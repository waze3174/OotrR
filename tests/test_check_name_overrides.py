"""Community display names of the checks: the spreadsheet converter and how the names are shown."""
import _src_path  # noqa: F401  (src on sys.path)
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from xml.sax.saxutils import escape

from oot_rando.game import check_name_overrides as overrides
from oot_rando.randomizer import spoiler_report
from oot_rando.tracker.check_labels import check_labels

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'check_name_overrides_from_xlsx.py'
spec = importlib.util.spec_from_file_location('check_name_overrides_from_xlsx', TOOL)
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)

CURRENT, NEW = converter.CURRENT_HEADER, converter.NEW_NAME_HEADER


def write_workbook(path, sheets):
    """A minimal .xlsx: ``sheets`` is ``{name: {row number: {column: text}}}``."""
    def sheet_xml(rows):
        body = ''.join(
            f'<row r="{number}">' + ''.join(
                f'<c r="{column}{number}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'
                for column, text in cells.items()) + '</row>'
            for number, cells in rows.items())
        return f'<worksheet xmlns="{converter.SPREADSHEET_NS[1:-1]}"><sheetData>{body}</sheetData></worksheet>'
    namespace = converter.SPREADSHEET_NS[1:-1]
    relationships = converter.RELATIONSHIP_NS[1:-1]
    package = converter.PACKAGE_REL_NS[1:-1]
    book = ''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(sheets, 1))
    rels = ''.join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('xl/workbook.xml',
                         f'<workbook xmlns="{namespace}" xmlns:r="{relationships}"><sheets>{book}</sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="{package}">{rels}</Relationships>')
        for i, rows in enumerate(sheets.values(), 1):
            archive.writestr(f'xl/worksheets/sheet{i}.xml', sheet_xml(rows))


FIXTURE = {
    'Tokens': {
        1: {'A': CURRENT, 'B': NEW, 'C': 'Logic'},
        2: {'A': 'Kokiri Forest'},
        3: {'A': 'KF gs 1', 'B': 'KF Bean Patch GS', 'C': 'is_child'},
        4: {'A': 'KF Twins House gs 1', 'B': ' KF  Twins House GS '},
        5: {'A': 'KF gs 9', 'C': 'has bottle'},
        6: {'A': 'LW gs 1 (child)', 'B': '*inaccessible'},
        7: {'A': 'LW gs 2', 'B': 'not randomized'},
        8: {'A': 'LW gs 3', 'B': 'LW gs 3'},
        9: {'A': 'Market', 'B': 'Hyrule Castle Town'},
    },
    # Header below the first row, the new names in column C, remarks in two more columns.
    'Chests': {
        1: {'A': 'a title row'},
        4: {'A': CURRENT, 'C': NEW, 'E': 'Logic', 'G': 'Testing?'},
        5: {'A': 'KF_chest_3', 'C': 'KF Storms Grotto Chest', 'E': 'has hookshot'},
        6: {'A': 'KF Storms Grotto Chest', 'C': '*no longer exists', 'G': 'does not register'},
        7: {'A': 'kak Open Grotto Chest', 'C': 'Kak Grotto Chest'},
        8: {'A': 'KF gs 1', 'C': 'KF Other GS', 'F': 'an untitled remark'},
        9: {'A': 'DC pot 1', 'C': 'DC First Pot'},
        10: {'A': 'DC_pot_1', 'C': 'DC Second Pot'},
    },
}


class Converter(unittest.TestCase):
    def convert(self, known=('Kak Open Grotto Chest', 'KF Storms Grotto Chest'), sheets=FIXTURE):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'names.xlsx'
            write_workbook(path, sheets)
            rows, remarks = converter.read_rows(converter.read_workbook(path))
        return converter.Conversion(rows, remarks, converter.KnownNames(known), False), remarks

    def test_rows_are_sorted_by_what_they_carry(self):
        conversion, _ = self.convert()
        self.assertEqual([r.current for r in conversion.headers], ['Kokiri Forest'])
        self.assertEqual([r.current for r in conversion.empty], ['KF gs 9'])
        self.assertEqual([r.current for r in conversion.notes], ['LW gs 1 (child)', 'KF Storms Grotto Chest'])
        self.assertEqual([r.current for r in conversion.unmarked_notes], ['LW gs 2'])
        self.assertEqual([r.current for r in conversion.unchanged], ['LW gs 3'])
        self.assertEqual([r.current for r in conversion.region_renames], ['Market'])

    def test_names_are_cleaned_and_matched_to_known_names(self):
        conversion, _ = self.convert()
        self.assertEqual(conversion.names['KF Twins House gs 1'], 'KF Twins House GS')
        self.assertEqual(conversion.names['KF_chest_3'], 'KF Storms Grotto Chest')
        self.assertEqual(conversion.names['Kak Open Grotto Chest'], 'Kak Grotto Chest')   # fuzzy: keyed by the real name
        self.assertEqual([(row.current, name) for row, name in conversion.fuzzy],
                         [('kak Open Grotto Chest', 'Kak Open Grotto Chest')])
        self.assertNotIn('LW gs 1 (child)', conversion.names)
        self.assertNotIn('KF gs 9', conversion.names)

    def test_conflicting_new_names_are_dropped(self):
        conversion, _ = self.convert()
        self.assertNotIn('KF gs 1', conversion.names)
        self.assertEqual([key for key, _ in conversion.conflicts], ['KF gs 1', 'DC pot 1 / DC_pot_1'])
        self.assertNotIn('DC pot 1', conversion.names)
        self.assertNotIn('DC_pot_1', conversion.names)

    def test_names_that_display_alike_are_listed(self):
        conversion, _ = self.convert()
        self.assertEqual(conversion.duplicates, {'kf storms grotto chest': ['KF Storms Grotto Chest', 'KF_chest_3']})

    def test_remarks_come_from_the_other_columns(self):
        _, remarks = self.convert()
        self.assertEqual([(sheet, row, text) for sheet, row, _, text in remarks],
                         [('Chests', 6, 'does not register'), ('Chests', 8, 'an untitled remark')])

    def test_ambiguous_known_names_are_not_applied(self):
        conversion, _ = self.convert(known=('Kak Open Grotto Chest', 'KAK open grotto chest'))
        self.assertNotIn('Kak Open Grotto Chest', conversion.names)
        self.assertEqual([row.current for row, _ in conversion.ambiguous], ['kak Open Grotto Chest'])

    def test_loose_forms_match_the_scan_labels(self):
        known = converter.KnownNames(['KF_gs_1 (child)', 'DC_room10_gs_1', 'Jabu_room14_gs_1',
                                      'GV_gs_3 (child)', 'GV_gs_3 (adult)'])
        self.assertEqual(known.resolve('KF gs 1'), ('fuzzy', 'KF_gs_1 (child)'))
        self.assertEqual(known.resolve('DC room 10 gs 1'), ('fuzzy', 'DC_room10_gs_1'))
        self.assertEqual(known.resolve('Jabu room 14 gs'), ('fuzzy', 'Jabu_room14_gs_1'))
        self.assertEqual(converter.KnownNames(['HC crate 1']).resolve('HC crate1'), ('fuzzy', 'HC crate 1'))
        # Both ages left out: two checks fit, neither is renamed.
        self.assertEqual(known.resolve('GV gs 3'), ('ambiguous', ['GV_gs_3 (adult)', 'GV_gs_3 (child)']))

    def test_with_a_catalogue_unknown_names_are_unmatched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'names.xlsx'
            write_workbook(path, FIXTURE)
            rows, remarks = converter.read_rows(converter.read_workbook(path))
        conversion = converter.Conversion(rows, remarks, converter.KnownNames(['KF_chest_3']), True)
        self.assertIn('KF Twins House gs 1', [row.current for row in conversion.unmatched])
        self.assertNotIn('KF_chest_3', [row.current for row in conversion.unmatched])

    def test_the_document_lists_the_names_sorted(self):
        conversion, _ = self.convert()
        document = converter.overrides_document(conversion, 'names.xlsx')
        self.assertEqual(document['source'], 'names.xlsx')
        self.assertEqual(list(document['names']), sorted(document['names']))


class Display(unittest.TestCase):
    NAMES = {'KF gs 1': 'KF Bean Patch GS', 'KF_pot_2 (child)': 'Near Know It All Brothers House Pot 1',
             'LW rock 1': 'First', 'LW_rock_1': 'Second', 'KF Kokiri Sword Chest': 'Sword Chest'}

    def test_exact_names_then_the_same_name_in_another_form(self):
        table = overrides.Overrides(self.NAMES)
        self.assertEqual(table.display('KF gs 1'), 'KF Bean Patch GS')
        self.assertEqual(table.display('KF_gs_1'), 'KF Bean Patch GS')
        self.assertEqual(table.display('kf pot 2 (child)'), 'Near Know It All Brothers House Pot 1')
        self.assertNotEqual(table.display('KF_pot_2 (adult)'), 'Near Know It All Brothers House Pot 1')

    def test_unknown_names_and_ambiguous_forms_are_left_alone(self):
        table = overrides.Overrides(self.NAMES)
        self.assertEqual(table.display('HF gs 1'), 'HF gs 1')
        self.assertEqual(table.display('LW_rock 1'), 'LW_rock 1')      # two names share this form
        self.assertEqual(table.display('LW rock 1'), 'First')          # an exact name still wins

    def test_the_shipped_file_maps_names_to_names(self):
        names = json.loads(overrides.resource(*overrides.OVERRIDES_RESOURCE).read_text(encoding='utf-8'))['names']
        self.assertTrue(names)
        for current, new in names.items():
            self.assertEqual(current, ' '.join(current.split()))
            self.assertEqual(new, ' '.join(new.split()))
            self.assertFalse(new.startswith(converter.NOTE_PREFIX), current)
            self.assertNotEqual(current, new)


class Applied(unittest.TestCase):
    CHECKS = [
        {'id': 'KokiriForest#pots#1', 'region': 'Kokiri Forest', 'name': 'KF_pot_2 (child)', 'category': 'full_pots'},
        {'id': 'KokiriForest#chest#9', 'region': 'Kokiri Forest', 'name': 'KF_chest_5', 'category': 'world_chests'},
        {'id': 'ap#KF Kokiri Sword Chest', 'region': 'Kokiri Forest', 'name': 'KF Kokiri Sword Chest',
         'category': 'vanilla_chest'},
        {'id': 'ap#HF Open Grotto Chest', 'region': 'Hyrule Field', 'name': 'HF Open Grotto Chest',
         'category': 'vanilla_chest'}]
    TABLE = overrides.Overrides({'KF pot 2 (child)': 'Near Know It All Brothers House Pot 1',
                                 'KF_chest_5': 'Never shown', 'KF Kokiri Sword Chest': 'Sword Chest'})

    def test_the_trackers_show_the_new_names_and_the_ids_stay(self):
        with mock.patch.object(overrides, 'load_overrides', return_value=self.TABLE):
            labels = check_labels(self.CHECKS)
        self.assertEqual(list(labels), [check['id'] for check in self.CHECKS])
        self.assertEqual(labels['KokiriForest#pots#1'], 'Near Know It All Brothers House Pot 1')
        self.assertEqual(labels['ap#KF Kokiri Sword Chest'], 'Sword Chest')
        self.assertEqual(labels['ap#HF Open Grotto Chest'], 'HF Open Grotto Chest')   # unknown name: unchanged
        self.assertEqual(labels['KokiriForest#chest#9'], 'Chest 2')                    # numbered, not renamed

    def test_turned_off_the_catalogue_names_show_again(self):
        with mock.patch.object(overrides, 'load_overrides', return_value=self.TABLE), \
                mock.patch.dict('os.environ', {}, clear=False):
            overrides.set_enabled(False)
            self.assertFalse(overrides.enabled())
            labels = check_labels(self.CHECKS)
            self.assertEqual(labels['KokiriForest#pots#1'], 'KF_pot_2 (child)')
            self.assertEqual(labels['ap#KF Kokiri Sword Chest'], 'KF Kokiri Sword Chest')
            overrides.set_enabled(True)
            self.assertTrue(overrides.enabled())
            self.assertEqual(check_labels(self.CHECKS)['ap#KF Kokiri Sword Chest'], 'Sword Chest')

    def test_the_catalogue_is_not_modified(self):
        before = json.dumps(self.CHECKS)
        with mock.patch.object(overrides, 'load_overrides', return_value=self.TABLE):
            check_labels(self.CHECKS)
        self.assertEqual(json.dumps(self.CHECKS), before)

    def test_the_spoiler_uses_the_new_names(self):
        spoiler = {'seed_id': 's', 'placements': [
            {'id': 'ap#KF Kokiri Sword Chest', 'location': 'KF Kokiri Sword Chest', 'item': 'Progressive Hookshot',
             'actor': 'Item_Hookshot', 'before': 'TBox_Rupee_Green', 'source': 'chest', 'category': 'full_chests'}],
            'playthrough': []}
        checks = {'checks': [dict(self.CHECKS[2], zone='KokiriForest')]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'spoiler.json').write_text(json.dumps(spoiler), encoding='utf-8')
            (root / 'checks.json').write_text(json.dumps(checks), encoding='utf-8')
            with mock.patch.object(overrides, 'load_overrides', return_value=self.TABLE):
                report = spoiler_report.load_report(root)
        self.assertEqual(report['rows'][0]['location'], 'Sword Chest')
        self.assertEqual(report['rows'][0]['id'], 'ap#KF Kokiri Sword Chest')


if __name__ == '__main__':
    unittest.main()
