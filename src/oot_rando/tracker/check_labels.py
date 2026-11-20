"""The names the trackers show for a seed's checks (the window's tracker and the in-game one)."""
from oot_rando.game.check_name_overrides import display_name

UNNAMED_CATEGORY = 'world_chests'   # chests the world randomizer adds: their catalogue names are internal


def check_labels(checks):
    """``{check id: name shown}`` for a catalogue: each check's name (renamed by ``check_name_overrides.json``),
    or ``Chest N`` for a chest of ``UNNAMED_CATEGORY`` (N counts every check of its region so far, in
    catalogue order)."""
    labels, numbers = {}, {}
    for check in checks:
        region = check.get('region') or 'Other'
        numbers[region] = numbers.get(region, 0) + 1
        named = check.get('category') != UNNAMED_CATEGORY
        labels[check['id']] = display_name(check['name']) if named else f'Chest {numbers[region]}'
    return labels
