"""Title screen badge (patching/title_badge.py)."""
import _src_path  # noqa: F401  (src on sys.path)
import os
import struct
import unittest

from oot_rando.patching import title_badge as tb

NUP = os.environ.get('OOT_NUP')


def fake_bntx(cols=420, rows=320, block_height=4):
    """A BNTX with one ASTC logo whose every block is the transparent void block."""
    gobs = (cols * 16 + 63) // 64
    size = ((rows + (8 << block_height) - 1) // (8 << block_height)) * (8 << block_height) * gobs * 64
    name = b'Logo_USEU_00'
    info, brti, name_at, mips_at, data_at = 0x40, 0x100, 0x200, 0x240, 0x400
    raw = bytearray(data_at + size)
    raw[:4] = b'BNTX'
    struct.pack_into('<Iq', raw, 0x24, 1, info)
    struct.pack_into('<q', raw, info, brti)
    raw[brti:brti + 4] = b'BRTI'
    struct.pack_into('<IIiiiii', raw, brti + 0x1C, tb.ASTC_4X4_SRGB, 0, cols * 4, rows * 4, 1, 1, block_height)
    struct.pack_into('<I', raw, brti + 0x50, size)
    struct.pack_into('<qqq', raw, brti + 0x60, name_at, 0, mips_at)
    struct.pack_into('<H', raw, name_at, len(name))
    raw[name_at + 2:name_at + 2 + len(name)] = name
    struct.pack_into('<q', raw, mips_at, data_at)
    raw[data_at:] = tb.TRANSPARENT * (size // 16)
    return bytes(raw)


class BadgeTests(unittest.TestCase):
    def test_badge_shape(self):
        cells = tb.badge_blocks()
        self.assertEqual({row for _, row in cells}, set(range(tb.BAND_ROWS)))
        self.assertEqual(min(col for col, _ in cells), 0)
        self.assertIn(tb.GOLD, cells.values())
        self.assertIn(tb.WHITE, cells.values())

    def test_void_block(self):
        self.assertEqual(tb.void_block((255, 255, 255, 0)), tb.TRANSPARENT)

    def test_drawn_in_the_empty_band_only(self):
        raw = fake_bntx()
        out, report = tb.add_title_badge(raw)
        self.assertEqual(len(out), len(raw))
        self.assertEqual(report, {'Logo_USEU_00': len(tb.badge_blocks())})
        changed = sum(1 for i in range(0, len(raw), 16) if raw[i:i + 16] != out[i:i + 16])
        self.assertEqual(changed, len(tb.badge_blocks()))
        with self.assertRaises(ValueError):   # never twice
            tb.add_title_badge(out)

    def test_block_linear_offsets_are_a_permutation(self):
        cols, rows = 20, 300
        offsets = {tb.block_offset(c, r, cols, 4) for c in range(cols) for r in range(rows)}
        self.assertEqual(len(offsets), cols * rows)
        self.assertTrue(all(o % 16 == 0 for o in offsets))

    @unittest.skipUnless(NUP, 'OOT_NUP not set')
    def test_every_regional_logo_of_the_game(self):
        from oot_rando.formats.inspect_nup import Nup
        from oot_rando.formats.inspect_resources import decompress, dictionaries
        nup = Nup(NUP)
        raw = decompress(nup.read(nup.latest('romfs/' + tb.TITLE_BNTX)), dictionaries(nup))
        out, report = tb.add_title_badge(raw)
        self.assertEqual(sorted(report), ['Logo_CNzh_00', 'Logo_JPja_00', 'Logo_KRko_00', 'Logo_TWzh_00',
                                          'Logo_USEU_00'])
        self.assertEqual(len(out), len(raw))


if __name__ == '__main__':
    unittest.main()
