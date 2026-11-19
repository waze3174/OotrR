"""Owl tutorials disappear without skipping quest work or losing the two rides."""
import _src_path  # noqa: F401
import os
import unittest

from oot_rando.patching import owl_advice as owl


class OwlFlags(unittest.TestCase):
    def test_only_safe_tutorials_are_premarked(self):
        flags = owl.start_values()
        self.assertEqual(len(flags), 8)
        self.assertTrue(all(value is True for value in flags.values()))
        for scene in ('Dm_TimeTemple_0086', 'Dm_HrlField_0080', 'Npc_Dream_FirstTalk',
                      'Dm_HrlField_0010', 'Dm_DeathMtTrail_0030', 'Dm_LakeHrl_0010'):
            self.assertNotIn('HavePlayedEvent.' + scene, flags)


@unittest.skipUnless(os.environ.get('OOT_NUP'), 'OOT_NUP not set')
class NativeOwls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import dictionaries
        from oot_rando.game.world_maps import effective_members
        cls.nup = Nup(os.environ['OOT_NUP'])
        cls.d = dictionaries(cls.nup)
        cls.members = effective_members(cls.nup)

    @classmethod
    def tearDownClass(cls):
        cls.nup.stream.close()

    def read(self, path):
        from oot_rando.formats.inspect_resources import decompress
        return decompress(self.nup.read(self.members[path]), self.d)

    @staticmethod
    def chart(raw):
        from oot_rando.patching.event_patch import _flow
        return _flow(raw).flowchart

    def test_all_premarked_flags_are_native_saved_bools(self):
        from oot_rando.formats.inspect_resources import Byml
        from oot_rando.patching.soul_adapter import GAMEDATA, murmur3
        entries = {e['Hash']: e for e in Byml(self.read(GAMEDATA)).root['Data']['Bool']}
        for name in owl.start_values():
            self.assertIn(murmur3(name), entries)
            self.assertGreaterEqual(entries[murmur3(name)]['SaveFileIndex'], 0)

    def test_first_field_scenes_mark_played_then_run_original_continuations(self):
        from oot_rando.patching.qol_patches import _predecessors
        raw = self.read(owl.CASTLE_FLOW)
        patched, report = owl.skip_first_field_advice(raw)
        before, after = self.chart(raw), self.chart(patched)
        events = {e.name: e for e in after.events}
        for name, details in report.items():
            self.assertFalse(_predecessors(after, events[name]))
            seen = events['RandoOwlSeen' + name]
            self.assertEqual(seen.data.actor_action.v.v, 'EventTriggerSetGameDataBool')
            self.assertEqual(seen.data.params.data,
                             {'GameDataName': 'HavePlayedEvent.' + details['scene'], 'Value': True, 'Index': -1})
            self.assertEqual(seen.data.nxt.v.name, details['resume'])
        # The native quest advance and environment reset are still present, unchanged.
        for name in ('Event14', 'Event217'):
            original = next(e for e in before.events if e.name == name)
            self.assertEqual(events[name].data.params.data, original.data.params.data)
            self.assertEqual(events[name].data.nxt.v.name, original.data.nxt.v.name)
        with self.assertRaises(ValueError):
            owl.skip_first_field_advice(patched)

    def test_dream_world_unlocks_without_forced_advice(self):
        patched, _ = owl.skip_dream_advice(self.read(owl.DREAM_INTRO_FLOW))
        chart = self.chart(patched)
        entry = next(e for e in chart.entry_points if e.name == 'EntryPoint0')
        self.assertEqual(entry.main_event.v.data.actor_action.v.v, 'EventTriggerSetGameDataBool')
        self.assertEqual(entry.main_event.v.data.params.data,
                         {'GameDataName': 'DreamWorld_Open', 'Value': True, 'Index': -1})
        wait = entry.main_event.v.data.nxt.v
        self.assertEqual(wait.data.actor_action.v.v, 'EventWaitCloseLoadingFade')
        reset = wait.data.nxt.v
        self.assertEqual(reset.data.actor_action.v.v, 'EventTriggerSendReserveCameraResetMessageToPlayerCamera')
        music = reset.data.nxt.v
        self.assertEqual(music.data.actor_action.v.v, 'EventTriggerSoundStartSceneBgm')
        self.assertIsNone(music.data.nxt.v)
        with self.assertRaises(ValueError):
            owl.skip_dream_advice(patched)

    def test_both_rides_keep_choice_loading_and_flight_without_advice(self):
        for path, fix, yes, resume, no in (
                (owl.DMT_FLOW, owl.short_mountain_ride, 'Event0', 'Event24', 'Event54'),
                (owl.LAKE_FLOW, owl.short_lake_ride, 'Event39', 'Event2', 'Event40')):
            with self.subTest(path=path):
                raw = self.read(path)
                before = self.chart(raw)
                patched, _ = fix(raw)
                chart = self.chart(patched)
                entries = {e.name: e for e in chart.entry_points}
                events = {e.name: e for e in chart.events}
                init = entries['Talk'].main_event.v
                self.assertEqual((init.data.res_flowchart_name, init.data.entry_point_name), ('InitTalk', 'InitTalk'))
                first = init.data.nxt.v
                if path == owl.LAKE_FLOW:
                    self.assertEqual(first.data.actor_action.v.v, 'EventTriggerParticipateEvent')
                    first = first.data.nxt.v
                self.assertEqual(first.name, 'Event13')
                self.assertEqual(first.data.params.data['ChoiceNumber'], 2)
                self.assertIsNone(entries['Near'].main_event.v)
                self.assertEqual(events[yes].data.nxt.v.name, resume)
                self.assertIsNone(events[no].data.nxt.v)
                # Yes/no switch and all original transition/reserve actions survive.
                for event in before.events:
                    action = getattr(event.data, 'actor_action', None)
                    if action and action.v.v in ('EventTransition', 'EventReserveBancChange',
                                                 'EventTriggerBancRequestBeforehandLoad'):
                        self.assertEqual(events[event.name].data.params.data, event.data.params.data)
                switch = events['Event14']
                self.assertEqual(set(switch.data.cases), {0, 1})
                self.assertEqual(switch.data.cases[1].v.name, no)
                with self.assertRaises(ValueError):
                    fix(patched)


if __name__ == '__main__':
    unittest.main()
