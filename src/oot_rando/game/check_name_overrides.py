"""Community display names for the tracker's checks (``check_name_overrides.json``).

The catalogue names a check after its Archipelago location or where it stands
(``game/check_names.py``). Players renamed many of them in a spreadsheet; the file maps a
check's current name to the name to show. Only what the trackers and the spoiler display
changes: a check's id, its catalogue entry and its Archipelago location stay as they are, so
a seed made before the renaming shows the new names too.

Rebuild the file from the spreadsheet with ``tools/check_name_overrides_from_xlsx.py``.

The names can be turned off (:func:`set_enabled`): the catalogue's own names show again. The
choice lives in the environment, so generation workers, which inherit it, follow it too.
"""
import functools
import json
import os
import re

from oot_rando.paths import resource

OVERRIDES_RESOURCE = ('game', 'check_name_overrides.json')
ENVIRONMENT = 'OOT_RANDO_CHECK_NAMES'   # 'original': show the catalogue's names


def normalize(name):
    """The name without case, punctuation or spacing: ``KF_pot_2 (child)`` and ``kf pot 2  child`` agree."""
    return re.sub(r'[^0-9a-z]+', ' ', name.casefold()).strip()


class Overrides:
    """``{current name: new name}``, looked up by exact name, then by normalized name when only one
    current name has that form."""

    def __init__(self, names):
        self.names = dict(names)
        forms = {}
        for name, new_name in self.names.items():
            forms.setdefault(normalize(name), set()).add(new_name)
        self.by_form = {form: next(iter(targets)) for form, targets in forms.items() if len(targets) == 1}

    def display(self, name):
        if name in self.names:
            return self.names[name]
        return self.by_form.get(normalize(name), name)


@functools.lru_cache(maxsize=None)
def load_overrides():
    path = resource(*OVERRIDES_RESOURCE)
    return Overrides(json.loads(path.read_text(encoding='utf-8'))['names'])


def enabled():
    """Whether the community names are shown."""
    return os.environ.get(ENVIRONMENT, '') != 'original'


def set_enabled(on):
    """Show the community names, or the catalogue's own names when ``on`` is false."""
    if on:
        os.environ.pop(ENVIRONMENT, None)
    else:
        os.environ[ENVIRONMENT] = 'original'


def display_name(name):
    """The name the trackers and the spoiler show for a check called ``name`` in the catalogue."""
    return load_overrides().display(name) if enabled() else name
