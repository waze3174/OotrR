"""Story locks of the remake that items found in any order would break.

The remake drives its story with *challenges* (RSDB ``Challenge``): a saved enum per
quest (``Get_StoneOfFire``: ``... SariaMelodyPlay, DodongoCavernOpne, ..., Complete``)
read through ``<Challenge>_IsAfter_<Step>_Exp`` / ``_IsCompleted_Exp`` BoolExps.
Several scenes assume the vanilla order of the quests. Each fix below is an exact
edit of one resource, checked by re-reading it (Discord reports of 15/11):

* **Darunia's gift** (``Dm_Goron_0030``, ``GC Darunias Joy``). Saria's Song played
  to Darunia runs ``Get_StoneOfFire/Get_StoneOfFire_PlayOcarina``: after his dance
  (``Dm_Goron_0025``) the gift scene plays only while the challenge is not past
  ``SariaMelodyPlay`` (Event39). Dodongo's Cavern finished first (bombs found
  early), the challenge is ``Complete`` and the gift never came. It now plays while
  ``HavePlayedEvent.Dm_Goron_0030`` is false. The gift scene itself moves the
  challenge to ``DodongoCavernOpne`` (Event121): that step is now skipped once the
  challenge is past ``SariaMelodyPlay``, so a finished quest never goes back.
* **Talon at the castle twice.** ``SubEvent_GetEponaSong/GetEponaSong_StepCheck``
  sends Malon back to the castle (``IsMalonAppear_HyruleCastleSecondTime``, with an
  awake Talon at the entrance) once Dodongo's Cavern is done and Jabu-Jabu is not.
  Vanilla never gets there before Talon was woken; done in another order, the first
  Malon (the Weird Egg) was hidden and the sleeping Talon stayed: no egg, no Zelda.
  Malon now only comes back after Talon's wake-up scene (``Dm_HrlCastle_0020``);
  before it the flag is cleared, which also repairs a save already in that state.
* **Sheik at the Master Sword.** In the Temple of Time (``Market_Adult_Static``),
  adult Sheik waits in front of the pedestal, so Link could not put the sword back
  before the Forest Temple (``SageOfForest``) was finished. He now only appears once
  that quest is complete (his talk is hints only: no quest step depends on it).
* **Bombchu Bowling.** The alley opened only after Dodongo's Cavern
  (``MiniGame_BombchuBowling/AfterWakeUp`` Event137, ``Get_StoneOfFire_IsCompleted_Exp``):
  it is open from the start, as the logic expects.
* **Great Fairies.** Zelda's Lullaby on a fountain's Triforce mark
  (``TriForcePoint/Sub_PlayOcarinaSequence_FairyFountain``) only calls the fairy of
  Din's Fire (Death Mountain Trail) at once; the five others stay away while
  ``IsGet.Item_DinFire`` is false (Event8), so with Din's Fire shuffled away they
  never came. Every fairy now answers the lullaby from the start; the way into
  each fountain (bombable wall, boulder...) is unchanged.
* **Great Fairy rewards given once, by the fairy.** On a later visit each fairy
  only heals Link when ``IsGet.<her vanilla item>`` is true (Din's Fire, magic,
  Farore's Wind...). That flag follows the item, not the fairy: Din's Fire found in
  a chest first, the Death Mountain fairy never handed over her shuffled reward.
  Each fairy now has her own saved flag (``RandoGreatFairy_<name>``), set right
  before her reward, and every test of her vanilla item in the fountain flows
  (and in ``TriForcePoint``, the six-fairy count of ``Meet_GreatFairy``) reads it.

Bool switches: case 0 = true, case 1 = false (as the vanilla flows). Not validated in game.
"""
import io

from oot_rando.patching.event_patch import GAMEDATA_ACTOR_PARAMS, _flow, _snapshot

FIRE_STONE_FLOW = 'Event/EventFlow/Get_StoneOfFire.bfevfl.zs'
DARUNIA_GIFT_FLOW = 'Event/EventFlow/Dm_Goron_0030.bfevfl.zs'
EPONA_FLOW = 'Event/EventFlow/SubEvent_GetEponaSong.bfevfl.zs'
BOWLING_FLOW = 'Event/EventFlow/MiniGame_BombchuBowling.bfevfl.zs'
FAIRY_CALL_FLOW = 'Event/EventFlow/TriForcePoint.bfevfl.zs'
FAIRY_CALL_GATE = 'IsGet.Item_DinFire'
# Great Fairy flows: (fountain, reward event, vanilla pouch actor).
GREAT_FAIRIES = (
    ('Din', 'Event212', 'Item_DinFire'), ('Power', 'Event141', 'Item_FairyBless_MP'),
    ('Frore', 'Event174', 'Item_FaroreWind'), ('Nayru', 'Event163', 'Item_NayruLove'),
    ('Wisdom', 'Event144', 'Item_FairyBless_MPDouble'), ('Courage', 'Event144', 'Item_FairyBless_DefenseDouble'),
)
GREAT_FAIRY_FLAG_PREFIX = 'RandoGreatFairy_'


def fairy_flow(name):
    return f'Event/EventFlow/Dm_FairyFountain_{name}.bfevfl.zs'


def fairy_flags():
    """``IsGet.<vanilla item>`` → the fairy's own saved flag, for every Great Fairy."""
    return {'IsGet.' + actor: GREAT_FAIRY_FLAG_PREFIX + name for name, _, actor in GREAT_FAIRIES}


def great_fairy_saved_flags():
    """Bools to register in GameData (false in a new save)."""
    return {flag: False for flag in fairy_flags().values()}
TEMPLE_MAP = 'Banc/Market/Market_Adult_Static.bcett.byml.zs'

DARUNIA_GIFT_PLAYED = 'HavePlayedEvent.Dm_Goron_0030'
AFTER_SARIA_PLAY = 'Get_StoneOfFire_IsAfter_SariaMelodyPlay_Exp'
TALON_AWAKE = 'HavePlayedEvent.Dm_HrlCastle_0020'
SECOND_MALON = 'IsMalonAppear_HyruleCastleSecondTime'
SHEIK = 'Npc_Hylia_Sheik_Adult'
SHEIK_PRESENCE = 'SageOfForest_IsCompleted_Exp'


class _Chart:
    """An event flow being edited: new events and the parameters they must keep."""

    def __init__(self, raw):
        self.flow = _flow(raw)
        self.chart = self.flow.flowchart
        self.expected = _snapshot(self.flow)
        self.events = {e.name: e for e in self.chart.events}

    def event(self, name, kind):
        if name not in self.events:
            raise ValueError('Unexpected event flow: no ' + name)
        event = self.events[name]
        if type(event.data).__name__ != kind:
            raise ValueError(f'Unexpected event flow: {name} is not a {kind}')
        return event

    def fresh(self, name):
        if name in self.events:
            raise ValueError('Story fix already applied: ' + name)

    def actor(self, name):
        from evfl.actor import Actor
        from evfl.common import ActorIdentifier
        from evfl.container import Container
        actor = next((a for a in self.chart.actors if str(a.identifier) == name), None)
        if actor is None:
            actor = Actor()
            actor.identifier = ActorIdentifier(name)
            actor.concurrent_clips = 1
            # A named actor without its parameter container crashes the game.
            actor.params = Container()
            actor.params.data = dict(GAMEDATA_ACTOR_PARAMS)
            self.chart.actors.append(actor)
        return actor

    @staticmethod
    def holder(collection, name):
        from evfl.common import StringHolder
        found = next((h for h in collection if h.v == name), None)
        if found is None:
            found = StringHolder(name)
            collection.append(found)
        return found

    def _add(self, name, data, params):
        from evfl.container import Container
        from evfl.event import Event
        self.fresh(name)
        data.params = Container()
        data.params.data = dict(params)
        event = Event()
        event.name, event.data = name, data
        self.chart.events.append(event)
        self.events[name] = event
        self.expected[name] = dict(params)
        return event

    def switch(self, name, query, params, true, false, actor='GameDataActor'):
        from evfl.event import SwitchEvent
        from evfl.util import make_index, make_rindex
        owner = self.actor(actor)
        data = SwitchEvent()
        data.actor = make_rindex(owner)
        data.actor_query = make_rindex(self.holder(owner.queries, query))
        # A case that ends the flow is left out (as the vanilla switches do).
        data.cases = {key: make_index(target) for key, target in ((0, true), (1, false)) if target is not None}
        return self._add(name, data, params)

    def action(self, name, actor, act, params, following):
        from evfl.event import ActionEvent
        from evfl.util import make_index, make_rindex
        owner = self.actor(actor)
        data = ActionEvent()
        data.actor = make_rindex(owner)
        data.actor_action = make_rindex(self.holder(owner.actions, act))
        data.nxt = make_index(following)
        return self._add(name, data, params)

    def set_bool(self, name, flag, value, following):
        return self.action(name, 'GameDataActor', 'EventTriggerSetGameDataBool',
                           {'GameDataName': flag, 'Value': value, 'Index': -1}, following)

    def write(self):
        stream = io.BytesIO()
        self.flow.write(stream)
        result = stream.getvalue()
        checked = _flow(result)
        if _snapshot(checked) != self.expected:
            raise ValueError('A story fix changed other parameters.')
        return result, {e.name: e for e in checked.flowchart.events}


def _params(event):
    return dict(event.data.params.data) if event.data.params is not None else {}


def _case(event, key):
    case = event.data.cases.get(key)
    return case.v if case is not None else None


def darunia_gift_after_dungeon(raw):
    """``Get_StoneOfFire``: the gift scene after the dance while it was never played.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    check = flow.event('Event39', 'SwitchEvent')
    gift, done = _case(check, 1), _case(check, 0)
    if (_params(check) != {'GameDataName': AFTER_SARIA_PLAY} or gift is None or done is None
            or type(gift.data).__name__ != 'ActionEvent'
            or _params(gift).get('EventName') != 'Dm_Goron_0030'):
        raise ValueError("Unexpected Darunia dance continuation.")
    given = flow.switch('RandoDaruniaGiftGiven', 'EventQueryIsGameDataBool',
                        {'GameDataName': DARUNIA_GIFT_PLAYED, 'Index': -1}, done, gift)
    check.data.cases[0] = make_index(given)
    result, events = flow.write()
    written = events['Event39'].data.cases
    switch = events['RandoDaruniaGiftGiven'].data.cases
    if (written[0].v.name != 'RandoDaruniaGiftGiven' or written[1].v.name != gift.name
            or switch[0].v.name != done.name or switch[1].v.name != gift.name):
        raise ValueError('Darunia gift wrongly chained.')
    return result, {'flow': FIRE_STONE_FLOW, 'switch': 'RandoDaruniaGiftGiven', 'flag': DARUNIA_GIFT_PLAYED}


def keep_fire_quest_forward(raw):
    """``Dm_Goron_0030``: the step ``DodongoCavernOpne`` only while not already past it.

    Returns (bytes, report)."""
    from oot_rando.patching.qol_patches import _predecessors
    from evfl.util import make_index
    flow = _Chart(raw)
    step = flow.event('Event121', 'ActionEvent')
    if (step.data.actor_action.v.v != 'EventExecuteProgressChallengeStep'
            or _params(step).get('ChallengeName') != 'Get_StoneOfFire'
            or _params(step).get('StepName') != 'DodongoCavernOpne'):
        raise ValueError('Unexpected Darunia gift step.')
    ui = step.data.nxt.v
    if (ui is None or type(ui.data).__name__ != 'ActionEvent'
            or ui.data.actor_action.v.v != 'EventTriggerShowChallengeProgressUI'):
        raise ValueError('Unexpected Darunia gift step continuation.')
    resume = ui.data.nxt.v
    links = _predecessors(flow.chart, step)
    if resume is None or len(links) != 1 or links[0][1] != 'nxt':
        raise ValueError('Unexpected Darunia gift step links.')
    guard = flow.switch('RandoFireQuestForward', 'EventQueryIsGameDataBoolExp',
                        {'GameDataName': AFTER_SARIA_PLAY}, resume, step)
    links[0][0].data.nxt = make_index(guard)
    result, events = flow.write()
    cases = events['RandoFireQuestForward'].data.cases
    if cases[0].v.name != resume.name or cases[1].v.name != 'Event121':
        raise ValueError('Darunia gift step wrongly guarded.')
    return result, {'flow': DARUNIA_GIFT_FLOW, 'switch': 'RandoFireQuestForward', 'skip_to': resume.name}


def second_malon_after_talon(raw):
    """``GetEponaSong_StepCheck``: Malon's second castle visit only once Talon is awake.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    jabu = flow.event('Event38', 'SwitchEvent')
    appear = _case(jabu, 1)
    if (_params(jabu) != {'GameDataName': 'Get_StoneOfWater_IsCompleted_Exp'} or appear is None
            or appear.name != 'Event36' or _params(appear) != {'GameDataName': SECOND_MALON, 'Value': True,
                                                                 'Index': -1}):
        raise ValueError('Unexpected Malon second visit check.')
    away = flow.set_bool('RandoMalonNotYetBack', SECOND_MALON, False, None)
    awake = flow.switch('RandoTalonAwake', 'EventQueryIsGameDataBool',
                        {'GameDataName': TALON_AWAKE, 'Index': -1}, appear, away)
    jabu.data.cases[1] = make_index(awake)
    result, events = flow.write()
    cases = events['RandoTalonAwake'].data.cases
    if (events['Event38'].data.cases[1].v.name != 'RandoTalonAwake' or cases[0].v.name != 'Event36'
            or cases[1].v.name != 'RandoMalonNotYetBack'
            or getattr(events['RandoMalonNotYetBack'].data.nxt, 'v', None) is not None):
        raise ValueError('Malon second visit wrongly chained.')
    return result, {'flow': EPONA_FLOW, 'switch': 'RandoTalonAwake', 'flag': TALON_AWAKE}


def open_bombchu_bowling(raw):
    """``AfterWakeUp``: the alley plays whether Dodongo's Cavern is done or not.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    gate = flow.event('Event137', 'SwitchEvent')
    opened, closed = _case(gate, 0), _case(gate, 1)
    if (_params(gate) != {'GameDataName': 'Get_StoneOfFire_IsCompleted_Exp'} or opened is None
            or closed is None or opened is closed):
        raise ValueError('Unexpected Bombchu Bowling gate.')
    gate.data.cases[1] = make_index(opened)
    result, events = flow.write()
    cases = events['Event137'].data.cases
    if cases[0].v.name != opened.name or cases[1].v.name != opened.name:
        raise ValueError('Bombchu Bowling gate not opened.')
    return result, {'flow': BOWLING_FLOW, 'gate': 'Event137', 'closed_talk': closed.name}


def open_great_fairies(raw):
    """``TriForcePoint``: every Great Fairy answers Zelda's Lullaby, Din's Fire held or not.

    Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    gate = flow.event('Event8', 'SwitchEvent')
    called, refused = _case(gate, 0), _case(gate, 1)
    ability = flow.event('Event132', 'SwitchEvent')
    if (_params(gate) != {'GameDataName': FAIRY_CALL_GATE, 'Index': -1} or called is None
            or refused is None or called is refused or _case(ability, 2) is not called):
        raise ValueError('Unexpected Great Fairy call gate.')
    gate.data.cases[1] = make_index(called)
    result, events = flow.write()
    cases = events['Event8'].data.cases
    if cases[0].v.name != called.name or cases[1].v.name != called.name:
        raise ValueError('Great Fairy call gate not opened.')
    return result, {'flow': FAIRY_CALL_FLOW, 'gate': 'Event8', 'flag': FAIRY_CALL_GATE,
                    'refusal': refused.name}


def _read_fairy_flags(flow):
    """Every Bool query of an item a Great Fairy gives now reads that fairy's flag."""
    replaced = []
    for name, event in flow.events.items():
        data = event.data
        if type(data).__name__ != 'SwitchEvent' or name.startswith('Rando'):
            continue
        if data.actor_query.v.v != 'EventQueryIsGameDataBool':
            continue
        params = data.params.data
        target = fairy_flags().get(params.get('GameDataName'))
        if target is None:
            continue
        if params.get('Index') != -1:
            raise ValueError('Unexpected Great Fairy item query: ' + name)
        params['GameDataName'] = target
        flow.expected[name]['GameDataName'] = target
        replaced.append(name)
    return sorted(replaced)


def _fairy_reward_flag(name, reward, actor):
    """``Dm_FairyFountain_<name>``: the fairy's flag set just before her reward; her
    item tests read it. Returns a fix ``raw -> (bytes, report)``."""
    def fix(raw):
        from oot_rando.patching.qol_patches import _predecessors
        from evfl.util import make_index
        flow = _Chart(raw)
        gift = flow.event(reward, 'SubFlowEvent')
        if (gift.data.res_flowchart_name != 'Dm_SY_GetInEvent'
                or not gift.data.entry_point_name.startswith('GetInEvent') or 'ActorName' not in _params(gift)):
            raise ValueError('Unexpected Great Fairy reward: ' + name)
        links = _predecessors(flow.chart, gift)
        if not links or any(kind == 'entry' for _, kind, _ in links):
            raise ValueError('Unexpected Great Fairy reward links: ' + name)
        flag = GREAT_FAIRY_FLAG_PREFIX + name
        marker = flow.set_bool('RandoGreatFairyGiven', flag, True, gift)
        for event, kind, key in links:
            if kind == 'nxt':
                event.data.nxt = make_index(marker)
            elif kind == 'case':
                event.data.cases[key] = make_index(marker)
            else:
                event.data.forks[key] = make_index(marker)
        replaced = _read_fairy_flags(flow)
        if not any(flow.events[e].data.params.data['GameDataName'] == flag for e in replaced):
            raise ValueError('Great Fairy without a test of her own item: ' + name)
        result, events = flow.write()
        given = events['RandoGreatFairyGiven']
        if given.data.nxt.v.name != reward or any(
                e.data.params is not None and e.data.params.data.get('GameDataName') == 'IsGet.' + actor
                for e in events.values() if type(e.data).__name__ == 'SwitchEvent'):
            raise ValueError('Great Fairy flag wrongly chained: ' + name)
        return result, {'flow': fairy_flow(name), 'flag': flag, 'before': reward, 'queries': replaced}
    return fix


def great_fairy_count(raw):
    """``TriForcePoint``: the six fairies of ``Check_Complete`` counted by their own
    flags (plus the opened call gate Event8, both cases alike).

    Applied after ``open_great_fairies`` (same flow). Returns (bytes, report)."""
    flow = _Chart(raw)
    replaced = _read_fairy_flags(flow)
    if replaced != sorted(['Event8', 'Event136', 'Event137', 'Event138', 'Event139', 'Event140', 'Event141']):
        raise ValueError('Unexpected Great Fairy count in TriForcePoint.')
    result, _ = flow.write()
    return result, {'flow': FAIRY_CALL_FLOW, 'queries': replaced}


def open_and_count_great_fairies(raw):
    """``TriForcePoint``: every fairy answers the lullaby; she is counted by her own flag."""
    opened, report = open_great_fairies(raw)
    result, counted = great_fairy_count(opened)
    return result, dict(report, queries=counted['queries'])


def sheik_presence_edits(root):
    """``patch_strings`` edits: adult Sheik of the Temple of Time after the Forest Temple."""
    found = [i for i, actor in enumerate(root.get('Actors', [])) if actor.get('Gyaml') == SHEIK]
    if len(found) != 1:
        raise ValueError('Temple of Time Sheik not found.')
    index = found[0]
    if 'Presence' in root['Actors'][index]:
        raise ValueError('Temple of Time Sheik already conditioned.')
    base = ('Actors', index, 'Presence')
    return [{'path': base + ('FlagName',), 'before': None, 'after': SHEIK_PRESENCE},
            {'path': base + ('IsCheckLazy',), 'before': None, 'after': False},
            {'path': base + ('IsNegation',), 'before': None, 'after': False}]


# The presence the fix gives the Temple of Time Sheik (as verify reads it back).
SHEIK_PRESENCE_ENTRY = {'FlagName': SHEIK_PRESENCE, 'IsCheckLazy': False, 'IsNegation': False}


# --- Zora's River mouth: no invisible wall for adult Link -------------------------
# Seven ``FldObj_AirWall_Player_GenerateNavMesh`` stand along the fence at the river
# mouth (ZoraRiver_Adult_Static, x -88..-56, z 5..7, baked in the X3_Z4 static
# compound), in one SimultaneousGroup with the two ``Obj_BrokenRock_A_01`` boulders.
# AP lets adult Link hop the fence (``is_adult or has_explosives``); the 0.6.2 logic
# asked for the boulder broken instead, but the wall still stopped adult Link in game
# (Discord, 16/11). Each wall now only exists for child Link (``Sequence_IsChildhood``,
# never true in the adult map), the way Mido's air wall depends on its flag. The child
# map keeps its walls: child Link still needs explosives, as in AP. Not validated in game.
ZORA_RIVER_MAP = 'Banc/ZoraRiver/ZoraRiver_Adult_Static.bcett.byml.zs'
ZORA_RIVER_WALL = 'FldObj_AirWall_Player_GenerateNavMesh'
ZORA_RIVER_WALLS = (4565321854739336115, 7850395794748438732, 7982339630050931435, 9371429508151251838,
                    11266001672277786960, 13781426553798151043, 14077907143773739344)
ZORA_RIVER_WALL_PRESENCE = 'Sequence_IsChildhood'
ZORA_RIVER_WALL_PRESENCE_ENTRY = {'FlagName': ZORA_RIVER_WALL_PRESENCE, 'IsCheckLazy': False,
                                  'IsNegation': False}


def zora_river_wall_edits(root):
    """``patch_strings`` edits: the river mouth walls of the adult map, child-only.

    Returns (edits, actor indices)."""
    found = {actor.get('Hash'): i for i, actor in enumerate(root.get('Actors', []))
             if actor.get('Hash') in ZORA_RIVER_WALLS}
    if set(found) != set(ZORA_RIVER_WALLS):
        raise ValueError("Zora's River mouth walls not found.")
    edits = []
    for ident in ZORA_RIVER_WALLS:
        actor = root['Actors'][found[ident]]
        if actor.get('Gyaml') != ZORA_RIVER_WALL or 'Presence' in actor:
            raise ValueError("Unexpected Zora's River mouth wall.")
        base = ('Actors', found[ident], 'Presence')
        edits += [{'path': base + (key,), 'before': None, 'after': value}
                  for key, value in ZORA_RIVER_WALL_PRESENCE_ENTRY.items()]
    return edits, sorted(found.values())


# --- Zelda's escape (DoorOfTime) on the Goron Ruby and the Zora Sapphire --------
# ``DoorOfTime/DoorOfTime_CheckStoneNum`` runs only at the end of Dodongo's Cavern and
# Jabu-Jabu's Belly and reads both dungeon *quests*: with the stones found elsewhere,
# Zelda never fled (15/11, Discord report). Its Step03 branch moves DoorOfTime to
# ``Step03``, raises the Hyrule Field drawbridge (``IsHyruleFieldBridgeClose``) and
# sets ``DoorOfTime_GetStoneCount`` to 0; the drawbridge area then starts
# ``HyruleField_DoorOfTime_Escape`` (Step04), then the moat ``..._GetOcarinaOfTime``.
# It reads only ``Get_StoneOfFire`` and ``Get_StoneOfWater`` (both done: Step03, one:
# Step2_1 or Step2_2, none: 2 stones left); the Kokiri Emerald and the Deku Tree are
# never checked, so the escape asks for the Goron Ruby and the Zora Sapphire only.
# The same branch now also runs on those two stones held, checked at every item get
# (``ActionGuide/ActionGuide``), at the end of Impa's send-off and at every dungeon end
# (before the native check), once DoorOfTime is past ``Step01`` (send-off done) and not
# past ``Step2_2`` (before Step03; ``IsAfter`` is strict, as Darunia's vanilla gift
# shows). The Hyrule Field drawbridge area (``HyruleField_Child_Prefab_0ce5``) exists
# only while the current step *is* Step03 (``HoldChallengeCurrentStepCheckOrder``
# IsEqual): the dungeon quests are never read. The native check is skipped once
# Step03 is reached, so a later dungeon end never moves it back (vanilla never runs it
# there). The send-off moves Get_StoneOfFire to ``KakarikoVillageNpc``: now only while
# that quest has not started (vanilla order), so Dodongo's Cavern done first stays done.
#
# 16/11 (Discord, 0.6.4): Zelda still waited for the dungeons. The added Step03 request
# lacked ``IsWaitEnd`` (the native one, which works at the dungeon end, has it): it now
# copies the native parameters exactly. Two talks also moved DoorOfTime back to
# ``Srep2_1_1`` (Zelda's ``AboutWaterStone`` with the Fire quest done, Saria's Song):
# both are now skipped once DoorOfTime is past ``Step2_1`` (:func:`door_of_time_forward`).
DOOR_FLOW = 'Event/EventFlow/DoorOfTime.bfevfl.zs'
ACTION_GUIDE_FLOW = 'Event/EventFlow/ActionGuide.bfevfl.zs'
STONES = ('Item_Stone_Fire', 'Item_Stone_Water')   # the native check's two quests
STONE_FLAG_PREFIX = 'IsGet.'   # saved when the stone is obtained, however it is given
DOOR_STARTED = 'DoorOfTime_IsAfter_Step01_Exp'
DOOR_BEFORE_ESCAPE = 'DoorOfTime_IsAfter_Step2_2_Exp'
BRIDGE_CLOSED = 'IsHyruleFieldBridgeClose'
FIRE_QUEST_STARTED = 'Get_StoneOfFire_IsAfter_Ready_Exp'
# ``DoorOfTime/Event37``, the native Step03 request, parameter for parameter.
DOOR_STEP03_PARAMS = {'IsIgnoreCompletedChallenge': False, 'IsIgnoreChallengeProgressUI': False,
                      'ChallengeName': 'DoorOfTime', 'IsWaitEnd': True, 'StepName': 'Step03'}


def _stone_check(flow, prefix, following, done=...):
    """Events: DoorOfTime to Step03 when started, before Step03, and the stones held.

    ``following``: where the flow goes on when the check does not pass; ``done``: after
    Step03 (``following`` by default)."""
    from evfl.util import make_index
    done = following if done is ... else done
    step = flow.action(prefix + 'Step03', 'ChallengeSystemActor', 'EventExecuteProgressChallengeStep',
                       DOOR_STEP03_PARAMS, None)
    bridge = flow.set_bool(prefix + 'Bridge', BRIDGE_CLOSED, True, None)
    count = flow.action(prefix + 'Count', 'GameDataActor', 'EventTriggerSetGameDataInt',
                        {'GameDataName': 'DoorOfTime_GetStoneCount', 'Value': 0, 'Index': -1}, done)
    step.data.nxt, bridge.data.nxt = make_index(bridge), make_index(count)
    check = step
    for index, stone in reversed(list(enumerate(STONES))):
        # The saved ``IsGet.<actor>`` flag: the pouch only answers to pouch names, never
        # to the actor name (EventQueryIsExistInPouch on Item_Stone_* was always false,
        # so Zelda still waited for the bosses; 15/11 report).
        check = flow.switch(f'{prefix}Stone{index}', 'EventQueryIsGameDataBool',
                            {'GameDataName': STONE_FLAG_PREFIX + stone, 'Index': -1}, check, following)
    before = flow.switch(prefix + 'BeforeEscape', 'EventQueryIsGameDataBoolExp',
                         {'GameDataName': DOOR_BEFORE_ESCAPE}, following, check)
    return flow.switch(prefix + 'Started', 'EventQueryIsGameDataBoolExp',
                       {'GameDataName': DOOR_STARTED}, before, following)


def zelda_escape_on_item_get(raw):
    """``ActionGuide/ActionGuide``: the stone check first, at every item get. Returns (bytes, report)."""
    from evfl.util import make_index
    flow = _Chart(raw)
    entry = {e.name: e for e in flow.chart.entry_points}.get('ActionGuide')
    if entry is None or entry.main_event.v is None:
        raise ValueError('Unexpected ActionGuide flow.')
    first = entry.main_event.v
    entry.main_event = make_index(_stone_check(flow, 'RandoDoorStones', first))
    result, events = flow.write()
    start = {e.name: e for e in _flow(result).flowchart.entry_points}['ActionGuide'].main_event.v
    if start.name != 'RandoDoorStonesStarted' or events['RandoDoorStonesCount'].data.nxt.v.name != first.name:
        raise ValueError('Stone check wrongly chained in ActionGuide.')
    return result, {'flow': ACTION_GUIDE_FLOW, 'start': start.name, 'stones': list(STONES)}


def zelda_escape_door_flow(raw):
    """``DoorOfTime``: stone check after the send-off, native check never backwards.

    Returns (bytes, report)."""
    from evfl.util import make_index
    from oot_rando.patching.qol_patches import _predecessors
    flow = _Chart(raw)
    entries = {e.name: e for e in flow.chart.entry_points}
    native = entries.get('DoorOfTime_CheckStoneNum')
    if native is None or native.main_event.v is None or native.main_event.v.name != 'Event38':
        raise ValueError('Unexpected DoorOfTime stone check.')
    # Dungeon end: the stones first (Step03 and done), else the native check (vanilla).
    dungeon_end = _stone_check(flow, 'RandoDungeonEndStones', native.main_event.v, done=None)
    guard = flow.switch('RandoDoorCheckForward', 'EventQueryIsGameDataBoolExp',
                        {'GameDataName': DOOR_BEFORE_ESCAPE}, None, dungeon_end)
    native.main_event = make_index(guard)
    # Send-off: Step02 (Event7), then Get_StoneOfFire KakarikoVillageNpc (Event62), end.
    step02, fire = flow.event('Event7', 'ActionEvent'), flow.event('Event62', 'ActionEvent')
    if (_params(step02).get('StepName') != 'Step02' or step02.data.nxt.v is not fire
            or _params(fire).get('StepName') != 'KakarikoVillageNpc'
            or getattr(fire.data.nxt, 'v', None) is not None or len(_predecessors(flow.chart, fire)) != 1):
        raise ValueError('Unexpected Impa send-off end.')
    stones = _stone_check(flow, 'RandoSendOffStones', None)
    fire.data.nxt = make_index(stones)
    started = flow.switch('RandoFireQuestStarted', 'EventQueryIsGameDataBoolExp',
                          {'GameDataName': FIRE_QUEST_STARTED}, stones, fire)
    step02.data.nxt = make_index(started)
    result, events = flow.write()
    if (events['Event7'].data.nxt.v.name != 'RandoFireQuestStarted'
            or events['Event62'].data.nxt.v.name != 'RandoSendOffStonesStarted'
            or events['RandoDoorCheckForward'].data.cases[1].v.name != 'RandoDungeonEndStonesStarted'
            or events['RandoDungeonEndStonesStarted'].data.cases[1].v.name != 'Event38'
            or events['RandoDungeonEndStonesCount'].data.nxt.v is not None):
        raise ValueError('DoorOfTime stone checks wrongly chained.')
    return result, {'flow': DOOR_FLOW, 'native_guard': 'RandoDoorCheckForward', 'send_off': 'RandoSendOffStones',
                    'dungeon_end': 'RandoDungeonEndStones'}


# DoorOfTime steps (``RSDB/Challenge``, checked against the table at generation).
DOOR_STEPS = ('Ready', 'Step01', 'Step02', 'Step2_1', 'Srep2_1_1', 'Step2_2', 'Step03', 'Step04', 'Step05', 'Step06')
ZELDA_FLOW = 'Event/EventFlow/Npc_Hylia_Zelda_Child.bfevfl.zs'
SARIA_SONG_FLOW = 'Event/EventFlow/Dm_SY_Ocarina_SariaSong.bfevfl.zs'
DOOR_BACK_REQUESTS = (ZELDA_FLOW, SARIA_SONG_FLOW)
DOOR_PAST_SREP = 'DoorOfTime_IsAfter_Step2_1_Exp'   # strict: Srep2_1_1 or later


def door_of_time_forward(raw):
    """``Srep2_1_1`` requests skipped once DoorOfTime is past Step2_1 (never backwards).

    Zelda's talk about the Water stone (Fire quest done) and Saria's Song request it
    without checking where DoorOfTime stands: with the stones found first it went back
    from Step03 and the drawbridge area disappeared. Returns (bytes, report)."""
    from oot_rando.patching import quest_guard
    result, report = quest_guard.guard_requests(raw, 'DoorOfTime', {'DoorOfTime': list(DOOR_STEPS)},
                                                ('Srep2_1_1',), DOOR_PAST_SREP, prefix='RandoDoorForward_')
    if not report['guarded']:
        raise ValueError('No Srep2_1_1 request to guard.')
    return result, report


# --- The clock before Zelda ------------------------------------------------------
# Until Impa's send-off (``HavePlayedEvent.Dm_HrlField_0020``) the remake holds the
# Hyrule Field clock at 15:00 (issue #40; native code, not in the game data): no night,
# so no night-only skulltulas, Dampé... before Zelda. The flag is now set at the end of
# the new-game opening: the clock runs from the start. The send-off itself still plays
# (Impa's talk starts it with a map change, not on this flag); the flag is otherwise
# read only by two child NPCs' lines (Npc_Hylia_043_Child, Npc_Hylia_Soldier_008_Child)
# and by the Zora River owl (Dm_ZoraRiver_0005, which also needs Saria's Song).
CLOCK_FLAG = 'HavePlayedEvent.Dm_HrlField_0020'


def story_start_values():
    """GameData values written at the end of the new-game opening (full mode)."""
    return {CLOCK_FLAG: True}


# --- First arrivals never move a quest back --------------------------------------
# An entrance plays its area presentation the first time it is used
# (``FieldAndDungeonEntranceEventRequestActor``: ``InitEventName`` while ``InitEventFlag``
# is false), and some of these scenes request a quest step without checking where the
# quest stands. Vanilla always uses that entrance first; a seed can reach the area
# another way, so the scene comes later and pulls the quest back (Discord 15/11: King
# Zora back in front of the fountain). Scan of the entrances of 1.1.1 (the others check
# the quest before their request):
#
# * Zora River -> Zora's Domain (``Goto_ZoraDomain``, ``HavePlayedEvent.Dm_Zora_0000``):
#   ``Get_StoneOfWater`` to ``Step03`` / ``Step03_Impa``. Zora's Domain reached first
#   from Lake Hylia, Ruto's Letter delivered (``Step07``): King Zora went back to his
#   throne in front of the fountain, the letter already spent.
# * Kakariko -> Death Mountain Trail (``DeathMountainTrail_Arrive``,
#   ``Get_StoneOfFire_DeathMtTrailIn``): ``Get_StoneOfFire`` to ``DeathMtTrailNpc``, even
#   once complete (``IsIgnoreCompletedChallenge`` false). The trail reached first from
#   Goron City (Lost Woods shortcut) or the crater.
# * Haunted Wasteland -> Desert Colossus (``FromWasteland_ArriveColossus``):
#   ``SageOfSpirit`` to ``Step04``. The Colossus reached first with the Requiem.
# * Hyrule Field / castle -> Market (``Goto_HyruleCastle_EntryMarket``):
#   ``Goto_HyruleCastle`` to ``Step02_01``, even once complete.
#
# Each request is now skipped once the quest is past its step or complete (one guard
# per expression, :func:`oot_rando.patching.quest_guard.guard_requests`). The scenes
# themselves still play. Not validated in game.
ARRIVE_FLOW = 'Event/EventFlow/Dm_SY_BancChangeArrive.bfevfl.zs'
CASTLE_FLOW = 'Event/EventFlow/Goto_HyruleCastle.bfevfl.zs'
FIRST_ARRIVAL_REQUESTS = {
    ARRIVE_FLOW: (('Get_StoneOfWater', ('Step03', 'Step03_Impa')), ('SageOfSpirit', ('Step04',))),
    FIRE_STONE_FLOW: (('Get_StoneOfFire', ('DeathMtTrailNpc',)),),
    CASTLE_FLOW: (('Goto_HyruleCastle', ('Step02_01',)),),
}
FORWARD_PREFIX = 'RandoArrivalForward'


def first_arrival_forward(path, raw, steps):
    """``raw`` (the flow at ``path``) where its first-arrival requests never move a quest back.

    ``steps``: the challenge table (:func:`oot_rando.patching.quest_guard.challenge_steps`).
    Returns (bytes, [(event, step, expression)])."""
    from oot_rando.patching import quest_guard
    guarded, index = [], 0
    for challenge, wanted in FIRST_ARRIVAL_REQUESTS[path]:
        guards = [(step, quest_guard.after_expression(challenge, step)) for step in wanted]
        guards.append((None, f'{challenge}_IsCompleted_Exp'))
        for step, expression in guards:
            raw, report = quest_guard.guard_requests(raw, challenge, steps, wanted if step is None else (step,),
                                                     expression, prefix=f'{FORWARD_PREFIX}{index}_')
            index += 1
            if not report['guarded']:
                raise ValueError(f'First arrival guard: no {challenge} request to guard in {path}')
            guarded += [(event, name, expression) for event, name, _ in report['guarded']]
    return raw, guarded


def keep_first_arrivals_forward(read_flow, challenges_raw):
    """Every flow of :data:`FIRST_ARRIVAL_REQUESTS`. ``read_flow(path)``: its current bytes.
    Returns ({path: bytes}, {path: guarded})."""
    from oot_rando.patching import quest_guard
    steps = quest_guard.challenge_steps(challenges_raw)
    if tuple(steps.get('DoorOfTime', ())) != DOOR_STEPS:
        raise ValueError('Unexpected DoorOfTime steps in the challenge table.')
    files, report = {}, {}
    for path in FIRST_ARRIVAL_REQUESTS:
        files[path], report[path] = first_arrival_forward(path, read_flow(path), steps)
    return files, report


FLOW_FIXES = (
    (FIRE_STONE_FLOW, 'darunia_gift', darunia_gift_after_dungeon),
    (DARUNIA_GIFT_FLOW, 'fire_quest_forward', keep_fire_quest_forward),
    (EPONA_FLOW, 'second_malon', second_malon_after_talon),
    (BOWLING_FLOW, 'bombchu_bowling', open_bombchu_bowling),
    (FAIRY_CALL_FLOW, 'great_fairies', open_and_count_great_fairies),
    *((fairy_flow(name), 'great_fairy_' + name.lower(), _fairy_reward_flag(name, reward, actor))
      for name, reward, actor in GREAT_FAIRIES),
    (DOOR_FLOW, 'zelda_escape', zelda_escape_door_flow),
    (ZELDA_FLOW, 'zelda_talk_forward', door_of_time_forward),
    (SARIA_SONG_FLOW, 'saria_song_forward', door_of_time_forward),
)
