"""Story locks of the remake (patching/story_fixes.py). NUP tests need OOT_NUP."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import unittest
from unittest import mock

from oot_rando.formats import byml_codec
from oot_rando.formats.byml_writer import patch_strings
from oot_rando.formats.inspect_resources import Byml
from oot_rando.patching import story_fixes as s

NUP = os.environ.get('OOT_NUP')


class SheikUnits(unittest.TestCase):
    def test_presence_added_to_the_only_sheik(self):
        raw = byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': [
            {'Gyaml': 'Obj_TimeTemple_MasterSword_A_01', 'Hash': 1},
            {'Gyaml': s.SHEIK, 'Hash': 2}]}})
        edits = s.sheik_presence_edits(Byml(raw).root)
        root = Byml(patch_strings(raw, edits)).root
        self.assertEqual(root['Actors'][1]['Presence'], s.SHEIK_PRESENCE_ENTRY)
        self.assertNotIn('Presence', root['Actors'][0])
        with self.assertRaises(ValueError):    # never applied twice
            s.sheik_presence_edits(root)
        with self.assertRaises(ValueError):    # no Sheik
            s.sheik_presence_edits({'Actors': [{'Gyaml': 'Npc_X'}]})


class ZoraRiverWallUnits(unittest.TestCase):
    @mock.patch.object(s, 'ZORA_RIVER_WALLS', tuple(range(10, 17)))   # 32-bit hashes in the fixture
    def test_river_mouth_walls_become_child_only(self):
        actors = [{'Gyaml': 'Obj_BrokenRock_A_01', 'Hash': 1}]
        actors += [{'Gyaml': s.ZORA_RIVER_WALL, 'Hash': h} for h in s.ZORA_RIVER_WALLS]
        actors.append({'Gyaml': s.ZORA_RIVER_WALL, 'Hash': 2})     # another wall of the map
        raw = byml_codec.dump({'endian': '<', 'version': 7, 'root': {'Actors': actors}})
        edits, indices = s.zora_river_wall_edits(Byml(raw).root)
        self.assertEqual(indices, list(range(1, 1 + len(s.ZORA_RIVER_WALLS))))
        root = Byml(patch_strings(raw, edits)).root
        for index in indices:
            self.assertEqual(root['Actors'][index]['Presence'], s.ZORA_RIVER_WALL_PRESENCE_ENTRY)
        self.assertNotIn('Presence', root['Actors'][0])
        self.assertNotIn('Presence', root['Actors'][-1])
        with self.assertRaises(ValueError):    # never applied twice
            s.zora_river_wall_edits(root)
        with self.assertRaises(ValueError):    # a wall missing
            s.zora_river_wall_edits({'Actors': actors[:3]})


@unittest.skipUnless(NUP, 'OOT_NUP not set')
class GameFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        cls.nup = Nup(NUP)
        cls.d = dictionaries(cls.nup)
        cls.decompress = staticmethod(decompress)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        return self.decompress(self.nup.read(self.nup.latest('romfs/' + path)), self.d)

    def chart(self, raw):
        from oot_rando.patching.event_patch import _flow
        return {e.name: e for e in _flow(raw).flowchart.events}

    def check_kept(self, source, raw):
        from oot_rando.patching.event_patch import _flow, _snapshot
        before, after = _snapshot(_flow(source)), _snapshot(_flow(raw))
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)

    def test_darunia_gift_while_never_played(self):
        source = self.read(s.FIRE_STONE_FLOW)
        raw, _ = s.darunia_gift_after_dungeon(source)
        events = self.chart(raw)
        check = events['Event39'].data            # past SariaMelodyPlay (quest done)...
        given = check.cases[0].v
        self.assertEqual(given.name, 'RandoDaruniaGiftGiven')
        self.assertEqual(given.data.params.data, {'GameDataName': s.DARUNIA_GIFT_PLAYED, 'Index': -1})
        self.assertEqual(given.data.cases[1].v.name, 'Event31')        # ...gift scene if never played
        self.assertEqual(given.data.cases[1].v.data.params.data['EventName'], 'Dm_Goron_0030')
        self.assertEqual(check.cases[1].v.name, 'Event31')             # vanilla path unchanged
        self.check_kept(source, raw)
        with self.assertRaises(ValueError):
            s.darunia_gift_after_dungeon(raw)

    def test_gift_scene_never_moves_the_quest_back(self):
        source = self.read(s.DARUNIA_GIFT_FLOW)
        raw, report = s.keep_fire_quest_forward(source)
        events = self.chart(raw)
        guard = next(e for e in events.values()
                     if getattr(e.data, 'nxt', None) is not None and e.data.nxt.v is not None
                     and e.data.nxt.v.name == 'RandoFireQuestForward')
        self.assertIsNotNone(guard)
        cases = events['RandoFireQuestForward'].data.cases
        self.assertEqual(cases[1].v.name, 'Event121')                  # vanilla: still before the step
        self.assertEqual(cases[0].v.name, report['skip_to'])           # quest already further
        self.check_kept(source, raw)

    def test_second_malon_waits_for_talon(self):
        source = self.read(s.EPONA_FLOW)
        raw, _ = s.second_malon_after_talon(source)
        events = self.chart(raw)
        awake = events['Event38'].data.cases[1].v
        self.assertEqual(awake.name, 'RandoTalonAwake')
        self.assertEqual(awake.data.params.data, {'GameDataName': s.TALON_AWAKE, 'Index': -1})
        self.assertEqual(awake.data.cases[0].v.name, 'Event36')
        away = awake.data.cases[1].v
        self.assertEqual(away.data.params.data, {'GameDataName': s.SECOND_MALON, 'Value': False, 'Index': -1})
        self.check_kept(source, raw)

    def test_bombchu_bowling_open(self):
        source = self.read(s.BOWLING_FLOW)
        raw, _ = s.open_bombchu_bowling(source)
        cases = self.chart(raw)['Event137'].data.cases
        self.assertIs(cases[0].v, cases[1].v)
        self.check_kept(source, raw)

    def test_great_fairies_open(self):
        source = self.read(s.FAIRY_CALL_FLOW)
        raw, report = s.open_great_fairies(source)
        cases = self.chart(raw)['Event8'].data.cases
        self.assertIs(cases[0].v, cases[1].v)
        self.assertNotEqual(cases[1].v.name, report['refusal'])
        self.check_kept(source, raw)

    def test_great_fairies_counted_by_their_flags(self):
        raw, report = s.open_and_count_great_fairies(self.read(s.FAIRY_CALL_FLOW))
        events = self.chart(raw)
        names = {events[e].data.params.data['GameDataName'] for e in report['queries']}
        self.assertEqual(names, set(s.fairy_flags().values()))
        self.assertIs(events['Event8'].data.cases[0].v, events['Event8'].data.cases[1].v)

    def test_great_fairy_reward_sets_her_own_flag(self):
        for name, reward, actor in s.GREAT_FAIRIES:
            with self.subTest(name):
                source = self.read(s.fairy_flow(name))
                raw, report = s._fairy_reward_flag(name, reward, actor)(source)
                events = self.chart(raw)
                given = events['RandoGreatFairyGiven']
                self.assertEqual(given.data.params.data,
                                 {'GameDataName': s.GREAT_FAIRY_FLAG_PREFIX + name, 'Value': True, 'Index': -1})
                self.assertEqual(given.data.nxt.v.name, reward)
                queried = {e.data.params.data.get('GameDataName') for e in events.values()
                           if type(e.data).__name__ == 'SwitchEvent' and e.data.params is not None}
                self.assertNotIn('IsGet.' + actor, queried)
                self.assertIn(s.GREAT_FAIRY_FLAG_PREFIX + name, queried)
                self.assertFalse(queried & {'IsGet.' + a for _, _, a in s.GREAT_FAIRIES})

    def test_great_fairy_flags_unique(self):
        self.assertEqual(len(s.great_fairy_saved_flags()), 6)

    def test_temple_sheik(self):
        raw = self.read(s.TEMPLE_MAP)
        root = Byml(patch_strings(raw, s.sheik_presence_edits(Byml(raw).root))).root
        sheik = [a for a in root['Actors'] if a.get('Gyaml') == s.SHEIK]
        self.assertEqual(len(sheik), 1)
        self.assertEqual(sheik[0]['Presence'], s.SHEIK_PRESENCE_ENTRY)

    def test_zora_river_walls(self):
        raw = self.read(s.ZORA_RIVER_MAP)
        before = Byml(raw).root
        edits, indices = s.zora_river_wall_edits(before)
        root = Byml(patch_strings(raw, edits)).root
        walls = [a for a in root['Actors'] if a.get('Hash') in s.ZORA_RIVER_WALLS]
        self.assertEqual(len(walls), 7)
        self.assertTrue(all(a['Presence'] == s.ZORA_RIVER_WALL_PRESENCE_ENTRY for a in walls))
        # Same walls as the boulders' simultaneous group; nothing else changes.
        group = next(g for g in before['SimultaneousGroups'] if set(s.ZORA_RIVER_WALLS) <= set(g))
        self.assertEqual(len(group), 9)
        for index, (a, b) in enumerate(zip(before['Actors'], root['Actors'])):
            if index not in indices:
                self.assertEqual(a, b)

    def test_zelda_escape_on_stones_at_item_get(self):
        from oot_rando.patching.qol_patches import ocarina_guide_on_get
        source = ocarina_guide_on_get(self.read(s.ACTION_GUIDE_FLOW))[0]
        raw, _ = s.zelda_escape_on_item_get(source)
        events = self.chart(raw)
        started = events['RandoDoorStonesStarted'].data
        self.assertEqual(started.params.data, {'GameDataName': s.DOOR_STARTED})
        before = started.cases[0].v.data                       # send-off done...
        self.assertEqual(before.params.data, {'GameDataName': s.DOOR_BEFORE_ESCAPE})
        check, held = before.cases[1].v, []                    # ...and Step03 not reached
        while check.name.startswith('RandoDoorStonesStone'):
            params = check.data.params.data            # the saved flag, not the pouch
            self.assertEqual(params['Index'], -1)
            held.append(params['GameDataName'].removeprefix(s.STONE_FLAG_PREFIX))
            check = check.data.cases[0].v
        self.assertEqual(held, ['Item_Stone_Fire', 'Item_Stone_Water'])   # no Kokiri Emerald
        native_step03 = self.chart(self.read(s.DOOR_FLOW))['Event37'].data.params.data
        self.assertEqual(check.data.params.data, native_step03)       # the native request, IsWaitEnd too
        bridge = check.data.nxt.v
        self.assertEqual(bridge.data.params.data, {'GameDataName': s.BRIDGE_CLOSED, 'Value': True, 'Index': -1})
        self.assertEqual(bridge.data.nxt.v.data.nxt.v.name, 'RandoOcarinaHeld')   # then the vanilla get
        self.check_kept(source, raw)

    def test_door_flow_send_off_and_native_check(self):
        source = self.read(s.DOOR_FLOW)
        raw, _ = s.zelda_escape_door_flow(source)
        events = self.chart(raw)
        guard = events['RandoDoorCheckForward'].data
        self.assertEqual(set(guard.cases), {1})                # Step03 reached: nothing
        # Dungeon end: the stones first, then the native dungeon check.
        stones = guard.cases[1].v
        self.assertEqual(stones.name, 'RandoDungeonEndStonesStarted')
        self.assertEqual(stones.data.cases[1].v.name, 'Event38')          # send-off not done: native
        check = stones.data.cases[0].v.data.cases[1].v                     # before Step03: the stones
        while check.name.startswith('RandoDungeonEndStonesStone'):
            self.assertEqual(check.data.cases[1].v.name, 'Event38')        # one missing: native
            check = check.data.cases[0].v
        self.assertEqual(check.data.params.data, events['Event37'].data.params.data)
        self.assertIsNone(events['RandoDungeonEndStonesCount'].data.nxt.v)  # Step03: native skipped
        # The native check reaches Step03 (Event37) on the Fire and Water quests alone.
        native, read = events['Event38'], []
        while native.name != 'Event37':
            read.append(native.data.params.data['GameDataName'])
            native = native.data.cases[0].v
        self.assertEqual(read, ['Get_StoneOfFire_IsCompleted_Exp', 'Get_StoneOfWater_IsCompleted_Exp'])
        started = events['Event7'].data.nxt.v.data             # after Step02 of the send-off
        self.assertEqual(started.params.data, {'GameDataName': s.FIRE_QUEST_STARTED})
        self.assertEqual(started.cases[1].v.name, 'Event62')   # fire quest moved only if not started
        self.assertEqual(started.cases[0].v.name, 'RandoSendOffStonesStarted')
        self.assertEqual(events['Event62'].data.nxt.v.name, 'RandoSendOffStonesStarted')
        self.check_kept(source, raw)

    def steps(self):
        from oot_rando.patching.quest_guard import CHALLENGES, challenge_steps
        return challenge_steps(self.read(CHALLENGES))

    def test_door_of_time_steps_match_the_table(self):
        self.assertEqual(tuple(self.steps()['DoorOfTime']), s.DOOR_STEPS)

    def test_zelda_and_saria_never_move_door_of_time_back(self):
        # 16/11: Zelda's talk (Fire quest done) and Saria's Song set DoorOfTime back to
        # Srep2_1_1 from Step03: the drawbridge area (current step = Step03) vanished.
        for path, request in ((s.ZELDA_FLOW, 'Event42'), (s.SARIA_SONG_FLOW, 'Event172')):
            with self.subTest(path=path):
                source = self.read(path)
                raw, report = s.door_of_time_forward(source)
                self.assertEqual([(e, step) for e, step, _ in report['guarded']], [(request, 'Srep2_1_1')])
                events = self.chart(raw)
                guard = events['RandoDoorForward_0'].data
                self.assertEqual(guard.params.data, {'GameDataName': s.DOOR_PAST_SREP})
                self.assertEqual(guard.cases[1].v.name, request)         # before: vanilla request
                self.assertNotIn(0, guard.cases)                         # past: nothing (request ended the flow)
                self.check_kept(source, raw)
                with self.assertRaises(ValueError):
                    s.door_of_time_forward(raw)

    def test_zora_domain_arrival_keeps_king_zora_moved(self):
        # Discord 15/11: Zora's Domain reached from Lake Hylia, the letter delivered,
        # then the first arrival from Zora River set the quest back to Step03.
        source = self.read(s.ARRIVE_FLOW)
        raw, guarded = s.first_arrival_forward(s.ARRIVE_FLOW, source, self.steps())
        events = self.chart(raw)
        # Impa met or not, then: past the step? complete? only then the request.
        choice = events['Event46'].data
        for case, step, event in ((0, 'Step03_Impa', 'Event45'), (1, 'Step03', 'Event44')):
            after = choice.cases[case].v.data
            self.assertEqual(after.params.data, {'GameDataName': f'Get_StoneOfWater_IsAfter_{step}_Exp'})
            done = after.cases[1].v.data
            self.assertEqual(done.params.data, {'GameDataName': 'Get_StoneOfWater_IsCompleted_Exp'})
            self.assertEqual(done.cases[1].v.name, event)
            self.assertNotEqual(after.cases[0].v.name, event)    # past it: skipped
        colossus = events['Event82'].data.nxt.v.data             # after the Colossus presentation
        self.assertEqual(colossus.params.data, {'GameDataName': 'SageOfSpirit_IsAfter_Step04_Exp'})
        self.assertEqual({e for e, _, _ in guarded}, {'Event44', 'Event45', 'Event76'})
        self.check_kept(source, raw)

    def test_trail_and_market_arrivals_keep_their_quests(self):
        steps = self.steps()
        for path, event in ((s.FIRE_STONE_FLOW, 'Event156'), (s.CASTLE_FLOW, 'Event51')):
            with self.subTest(path=path):
                source = self.read(path)
                raw, guarded = s.first_arrival_forward(path, source, steps)
                self.assertIn(event, {e for e, _, _ in guarded})
                self.check_kept(source, raw)
        files, report = s.keep_first_arrivals_forward(self.read, self.read('RSDB/Challenge.Product.111.rstbl.byml.zs'))
        self.assertEqual(set(files), set(s.FIRST_ARRIVAL_REQUESTS))

    def test_arrival_expressions_exist(self):
        from oot_rando.patching.quest_guard import check_expressions, after_expression
        from oot_rando.patching.soul_adapter import GAMEDATA
        names = []
        for requests in s.FIRST_ARRIVAL_REQUESTS.values():
            for challenge, wanted in requests:
                names += [after_expression(challenge, step) for step in wanted]
                names.append(f'{challenge}_IsCompleted_Exp')
        check_expressions(self.read(GAMEDATA), names)

    def test_flags_exist_in_the_game_data(self):
        from oot_rando.patching.soul_adapter import GAMEDATA, murmur3
        data = Byml(self.read(GAMEDATA)).root['Data']
        bools = {e['Hash'] for e in data['Bool']}
        exps = {e['Hash'] for e in data['BoolExp']}
        stone_flags = tuple(s.STONE_FLAG_PREFIX + stone for stone in s.STONES)
        for name in (s.DARUNIA_GIFT_PLAYED, s.TALON_AWAKE, s.SECOND_MALON, s.BRIDGE_CLOSED, s.CLOCK_FLAG) + stone_flags:
            self.assertIn(murmur3(name), bools, name)
        for name in (s.AFTER_SARIA_PLAY, s.SHEIK_PRESENCE, s.DOOR_STARTED, s.DOOR_BEFORE_ESCAPE,
                     s.FIRE_QUEST_STARTED, s.DOOR_PAST_SREP):
            self.assertIn(murmur3(name), exps, name)


if __name__ == '__main__':
    unittest.main()
