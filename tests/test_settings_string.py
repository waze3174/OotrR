import _src_path  # noqa: F401  (src on sys.path)
import base64
import json
import unittest
import zlib

from oot_rando.logic import rando_options
from oot_rando.randomizer import settings_string
from oot_rando.randomizer.randomizer_core import GENERATOR_VERSION, Settings, CHESTS


def full_settings(seed='partie é 42', **options):
    full = rando_options.preset('ap_defaults')
    full.update(options)
    settings = Settings(seed, randomize_chests=False, full=full, skip_chest_cutscenes=True)
    settings.categories = dict.fromkeys(settings.categories, False)
    return settings.validate()


class SeedStringTests(unittest.TestCase):
    def test_round_trip_default_and_full(self):
        for settings in (Settings('abc'), Settings('x', open_forest=False, excluded_checks=[str(next(iter(CHESTS)))]),
                         full_settings(), full_settings(shuffle_pots='all')):
            with self.subTest(settings=settings.to_dict()):
                text = settings_string.encode(settings)
                self.assertTrue(text.startswith(settings_string.PREFIX))
                decoded, version = settings_string.decode(text)
                self.assertEqual(decoded.to_dict(), settings.to_dict())
                self.assertEqual(version, GENERATOR_VERSION)

    def test_stones_travel_with_the_string_and_older_strings_stay_vanilla(self):
        def payload_of(text):
            return json.loads(zlib.decompress(base64.urlsafe_b64decode(text[len(settings_string.PREFIX):] + '===')))

        for value in ('all', 'vanilla'):
            with self.subTest(spiritual_stones=value):
                decoded, _ = settings_string.decode(settings_string.encode(full_settings(spiritual_stones=value)))
                self.assertEqual(decoded.full['spiritual_stones'], value)
        # "Require all" is written although it is the default: a string without the option is older.
        self.assertEqual(payload_of(settings_string.encode(full_settings()))['s']['full']['spiritual_stones'], 'all')
        older = settings_string.encode(full_settings(spiritual_stones='vanilla'))
        self.assertNotIn('spiritual_stones', payload_of(older)['s'].get('full', {}))
        self.assertEqual(settings_string.decode(older)[0].full['spiritual_stones'], 'vanilla')

    def test_short_and_tolerant(self):
        text = settings_string.encode(full_settings())
        self.assertLess(len(text), 400)
        spaced = text[:20] + '\n ' + text[20:] + '  '
        self.assertEqual(settings_string.decode(spaced)[0].to_dict(), full_settings().to_dict())

    def test_previous_generator_string_keeps_its_version_for_the_import_warning(self):
        settings = full_settings()
        text = settings_string.encode(settings)
        payload = json.loads(zlib.decompress(base64.urlsafe_b64decode(text[len(settings_string.PREFIX):] + '===')))
        for historical_version in ('0.9.0', '0.10.0'):
            with self.subTest(version=historical_version):
                payload['v'] = historical_version
                historical = settings_string.PREFIX + base64.urlsafe_b64encode(zlib.compress(json.dumps(payload).encode())).decode()
                decoded, version = settings_string.decode(historical)
                self.assertEqual(decoded.to_dict(), settings.to_dict())
                self.assertEqual(version, historical_version)
                self.assertNotEqual(version, GENERATOR_VERSION)

    def test_rejects_garbage(self):
        good = settings_string.encode(Settings('abc'))
        for text in ('', 'hello', 'OOTR-', 'OOTR-!!!!', good[:-6],
                     'OOTR-' + base64.urlsafe_b64encode(zlib.compress(b'[1]')).decode()):
            with self.subTest(text=text), self.assertRaises(ValueError):
                settings_string.decode(text)

    def test_rejects_invalid_settings(self):
        data = json.dumps({'v': GENERATOR_VERSION, 's': {'seed': 'a', 'unknown': 1}}).encode()
        with self.assertRaises(ValueError):
            settings_string.decode('OOTR-' + base64.urlsafe_b64encode(zlib.compress(data)).decode())

    def test_zip_bomb_refused(self):
        data = zlib.compress(b'{"v":"1","s":{"seed":"' + b'a' * 1000000 + b'"}}', 9)
        with self.assertRaises(ValueError):
            settings_string.decode('OOTR-' + base64.urlsafe_b64encode(data).decode())


if __name__ == '__main__':
    unittest.main()
