"""Developer tool: build ``src/oot_rando/game/check_name_overrides.json`` from the community naming spreadsheet.

Each sheet lists the tracker's current check names in column A ("Tracker Region and Location") and
the new name beside them (column "New Location Name"; its column differs by sheet and the header may
sit below the first row). Only the standard library reads the workbook.

* an empty new name means "not done yet": the check keeps its name;
* a new name starting with ``*``, or that says the check is not randomized or does not exist, is a
  note: it is reported and skipped;
* a current name is matched to the Archipelago location names, and to the catalogue(s) given with
  ``--catalogue`` (a seed's ``checks.json``), exactly or, when only one name has the same form,
  by case, punctuation and spacing (reported as fuzzy). Names of the remake's own checks
  (``KF_pot_2``) are in no table here: without a catalogue they stay unverified and the file keys
  them as written. At run time the display falls back to the same normalized form;
* a current name given two different new names is dropped and reported.

    python tools/check_name_overrides_from_xlsx.py "Token and Check naming.xlsx" [--catalogue checks.json ...]
"""
import argparse
import json
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from oot_rando.game.check_name_overrides import normalize  # noqa: E402
from oot_rando.game.remake_world import ZONE_LABELS  # noqa: E402
from oot_rando.logic.world import World  # noqa: E402

DEFAULT_OUTPUT = ROOT / 'src' / 'oot_rando' / 'game' / 'check_name_overrides.json'
CURRENT_HEADER = 'Tracker Region and Location'
NEW_NAME_HEADER = 'New Location Name'
NOTE_PREFIX = '*'
UNMARKED_NOTE = re.compile(r'^(not randomi[sz]ed|no longer exists?|does not exist|null|not a check)\b', re.IGNORECASE)
REGION_NAMES = set(ZONE_LABELS.values())
REVIEWED_HEADERS = {'Testing?'}   # columns where a cell is a tester's remark, not logic
SPREADSHEET_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RELATIONSHIP_NS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PACKAGE_REL_NS = '{http://schemas.openxmlformats.org/package/2006/relationships}'


def _column(reference):
    return re.match(r'[A-Z]+', reference).group()


def _shared_strings(archive):
    if 'xl/sharedStrings.xml' not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read('xl/sharedStrings.xml'))
    return [''.join(t.text or '' for t in item.iter(SPREADSHEET_NS + 't')) for item in root.findall(SPREADSHEET_NS + 'si')]


def _cell_text(cell, strings):
    kind = cell.get('t')
    if kind == 'inlineStr':
        return ''.join(t.text or '' for t in cell.iter(SPREADSHEET_NS + 't'))
    value = cell.find(SPREADSHEET_NS + 'v')
    if value is None or value.text is None:
        return ''
    return strings[int(value.text)] if kind == 's' else value.text


def _sheet_paths(archive):
    """``{sheet name: path of its xml in the archive}``."""
    targets = {rel.get('Id'): rel.get('Target')
               for rel in ElementTree.fromstring(archive.read('xl/_rels/workbook.xml.rels')).iter(PACKAGE_REL_NS + 'Relationship')}
    book = ElementTree.fromstring(archive.read('xl/workbook.xml'))
    paths = {}
    for sheet in book.find(SPREADSHEET_NS + 'sheets'):
        target = targets[sheet.get(RELATIONSHIP_NS + 'id')]
        paths[sheet.get('name')] = target.lstrip('/') if target.startswith('/') else 'xl/' + target
    return paths


def read_workbook(path):
    """``{sheet name: [(row number, {column letter: text})]}``, empty cells left out."""
    sheets = {}
    with zipfile.ZipFile(path) as archive:
        strings = _shared_strings(archive)
        for name, sheet_path in _sheet_paths(archive).items():
            rows = []
            for row in ElementTree.fromstring(archive.read(sheet_path)).find(SPREADSHEET_NS + 'sheetData'):
                cells = {_column(cell.get('r')): _cell_text(cell, strings) for cell in row}
                cells = {column: text for column, text in cells.items() if text.strip()}
                if cells:
                    rows.append((int(row.get('r')), cells))
            sheets[name] = rows
    return sheets


def clean(text):
    """The text without surrounding or repeated whitespace."""
    return ' '.join(text.split())


def is_note(text):
    return text.startswith(NOTE_PREFIX) or bool(UNMARKED_NOTE.match(text))


class Row:
    def __init__(self, sheet, number, current, new):
        self.sheet, self.number, self.current, self.new = sheet, number, current, new

    def where(self):
        return f'{self.sheet} row {self.number}'


def _header(rows):
    """The (position in ``rows``, new-name column, header cells) of a sheet's header row, or None."""
    for position, (_, cells) in enumerate(rows):
        if cells.get('A') == CURRENT_HEADER:
            new_columns = [column for column, text in cells.items() if text == NEW_NAME_HEADER]
            if new_columns:
                return position, new_columns[0], cells
    return None


def read_rows(workbook):
    """``(rows, remarks)``: every named row below a sheet's header, and the cells of the other columns
    that read as a tester's remark (a ``*`` note, a ``Testing?`` cell, or a cell under no header)."""
    rows, remarks = [], []
    for sheet, sheet_rows in workbook.items():
        header = _header(sheet_rows)
        if header is None:
            continue
        position, new_column, titles = header
        for number, cells in sheet_rows[position + 1:]:
            current = clean(cells.get('A', ''))
            if not current:
                continue
            rows.append(Row(sheet, number, current, clean(cells.get(new_column, ''))))
            for column, text in cells.items():
                untitled = column not in titles
                if column not in ('A', new_column) and (text.startswith(NOTE_PREFIX) or untitled
                                                        or titles[column] in REVIEWED_HEADERS):
                    remarks.append((sheet, number, current, clean(text)))
    return rows, remarks


def loose_form(name):
    """The normalized name, also without the ways the sheet writes the scan's labels differently:
    ``DC room 10 gs`` and ``DC_room10_gs_1 (child)`` agree (a number set apart from the word before
    it, a missing index taken as 1, the age left out)."""
    form = re.sub(r'([a-z])(\d)', r'\1 \2', normalize(name))
    form = re.sub(r' (child|chld|adult)$', '', form)
    return re.sub(r'\bgs$', 'gs 1', form)


class KnownNames:
    """The names of real checks, by exact name, by normalized form and by loose form."""

    def __init__(self, names):
        self.names = set(names)
        self.by_form = defaultdict(set)
        self.by_loose_form = defaultdict(set)
        for name in self.names:
            self.by_form[normalize(name)].add(name)
            self.by_loose_form[loose_form(name)].add(name)

    def resolve(self, current):
        """``(kind, name or sorted candidates)``: exact, fuzzy (one name of that form, normalized or
        loose), ambiguous or unknown."""
        if current in self.names:
            return 'exact', current
        candidates = sorted(self.by_form.get(normalize(current), ()))
        if not candidates:
            candidates = sorted(self.by_loose_form.get(loose_form(current), ()))
        if len(candidates) == 1:
            return 'fuzzy', candidates[0]
        return ('ambiguous', candidates) if candidates else ('unknown', current)


def ap_location_names():
    return set(World().location_table)


def catalogue_names(paths):
    names = set()
    for path in paths:
        names.update(check['name'] for check in json.loads(Path(path).read_text(encoding='utf-8'))['checks'])
    return names


class Conversion:
    """What a spreadsheet turned into: the overrides and everything that was set aside."""

    def __init__(self, rows, remarks, known, has_catalogue):
        self.rows, self.remarks, self.has_catalogue = rows, remarks, has_catalogue
        self.empty, self.headers, self.notes, self.unmarked_notes = [], [], [], []
        self.region_renames, self.unchanged, self.ambiguous = [], [], []
        self.fuzzy, self.unverified, self.unmatched, self.whitespace = [], [], [], []
        self.conflicts, self.parentheses = [], []
        self.keys = {}    # row -> the name the override is keyed by
        self.names = self._convert(known)
        self.duplicates = self._duplicate_names()

    def _convert(self, known):
        proposals = defaultdict(list)    # key -> [(row, new name)]
        for row in self.rows:
            if not self._sort(row):
                continue
            key = self._key(row, known)
            if key is not None:
                proposals[key].append((row, row.new))
        names = self._without_conflicts(proposals)
        self._drop_conflicting_forms(names)
        return dict(sorted(names.items()))

    def _sort(self, row):
        """Whether the row carries a usable new name (the others are listed by kind)."""
        if not row.new:
            (self.headers if row.current in REGION_NAMES else self.empty).append(row)
        elif row.current in REGION_NAMES:
            self.region_renames.append(row)
        elif row.new.startswith(NOTE_PREFIX):
            self.notes.append(row)
        elif is_note(row.new):
            self.unmarked_notes.append(row)
        elif row.new == row.current:
            self.unchanged.append(row)
        else:
            return True
        return False

    def _key(self, row, known):
        kind, found = known.resolve(row.current)
        if kind == 'ambiguous':
            self.ambiguous.append((row, found))
            return None
        if kind == 'fuzzy':
            self.fuzzy.append((row, found))
        elif kind == 'unknown':
            (self.unmatched if self.has_catalogue else self.unverified).append(row)
        if row.new.count('(') != row.new.count(')'):
            self.parentheses.append(row)
        self.keys[row] = found
        return found

    def _without_conflicts(self, proposals):
        names = {}
        for key, entries in proposals.items():
            targets = {new for _, new in entries}
            if len(targets) == 1:
                names[key] = targets.pop()
            else:
                self.conflicts.append((key, entries))
        return names

    def _drop_conflicting_forms(self, names):
        """Two keys with one normalized form and different new names would be ambiguous at run time."""
        forms = defaultdict(list)
        for key in names:
            forms[normalize(key)].append(key)
        for keys in forms.values():
            if len({names[key] for key in keys}) > 1:
                self.conflicts.append((' / '.join(keys), [(None, names.pop(key)) for key in keys]))

    def _duplicate_names(self):
        """Groups of checks that would display the same name, at least one of them renamed."""
        shown = defaultdict(set)
        for row in self.rows:
            if row.current in REGION_NAMES:
                continue
            key = self.keys.get(row, row.current)
            shown[normalize(self.names.get(key, row.current))].add(key)
        return {form: sorted(keys) for form, keys in shown.items()
                if len(keys) > 1 and any(key in self.names for key in keys)}


def build_conversion(path, catalogue_paths=()):
    rows, remarks = read_rows(read_workbook(path))
    catalogue = catalogue_names(catalogue_paths)
    return Conversion(rows, remarks, KnownNames(ap_location_names() | catalogue), bool(catalogue))


def overrides_document(conversion, source):
    return {'source': source, 'names': conversion.names}


def _section(title, items, show=lambda item: str(item)):
    lines = [f'{title}: {len(items)}']
    lines += ['  ' + show(item) for item in items]
    return lines


def report(conversion):
    rows = conversion.rows
    where = lambda row: f'{row.where()}: {row.current!r} -> {row.new!r}'
    lines = [f'rows read: {len(rows)}',
             f'overrides written: {len(conversion.names)}',
             f'empty (not done yet): {len(conversion.empty)}, area headers: {len(conversion.headers)}',
             f'skipped as notes: {len(conversion.notes)} starred, {len(conversion.unmarked_notes)} unmarked',
             f'new name equal to the current one: {len(conversion.unchanged)}',
             f'fuzzy matches: {len(conversion.fuzzy)}, unmatched: {len(conversion.unmatched)}, '
             f'unverified (no table to check against): {len(conversion.unverified)}, '
             f'ambiguous: {len(conversion.ambiguous)}, conflicts: {len(conversion.conflicts)}']
    lines += _section('region renames (not applied)', conversion.region_renames, where)
    lines += _section('starred notes', conversion.notes, where)
    lines += _section('unmarked notes', conversion.unmarked_notes, where)
    lines += _section('fuzzy matches', conversion.fuzzy, lambda item: f'{item[0].where()}: {item[0].current!r} ~ {item[1]!r}')
    lines += _section('ambiguous (not applied)', conversion.ambiguous, lambda item: f'{item[0].where()}: {item[0].current!r} ~ {item[1]}')
    lines += _section('unmatched', conversion.unmatched, lambda row: f'{row.where()}: {row.current!r}')
    lines += _section('conflicting new names (not applied)', conversion.conflicts,
                      lambda item: f'{item[0]!r}: {[new for _, new in item[1]]}')
    lines += _section('new names shared by several checks', list(conversion.duplicates.items()),
                      lambda item: f'{item[0]!r}: {item[1]}')
    lines += _section('new names with unbalanced parentheses', conversion.parentheses, where)
    lines += _section('tester remarks in the other columns', conversion.remarks,
                      lambda item: f'{item[0]} row {item[1]} ({item[2]!r}): {item[3]}')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('spreadsheet', type=Path)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--catalogue', type=Path, action='append', default=[],
                        help="a seed's checks.json, to check the names against (repeatable)")
    args = parser.parse_args(argv)
    conversion = build_conversion(args.spreadsheet, catalogue_paths=args.catalogue)
    document = overrides_document(conversion, args.spreadsheet.name)
    args.out.write_text(json.dumps(document, ensure_ascii=False, indent=1, sort_keys=False) + '\n', encoding='utf-8')
    print(report(conversion))


if __name__ == '__main__':
    main()
