"""A "Randomizer" badge (triforce + word) on the title screen logo.

Players and viewers see at once that a seed is installed. The title logo is a texture
of ``UI/Layout2Archive/Title…bntx`` (one per region: ``Logo_USEU_00``, ``Logo_JPja_00``…),
ASTC 4x4 sRGB, 1664x1280, Tegra block-linear layout. Its bottom band (the last 16 block
rows, 64 texels) is empty: every block there is an ASTC *void-extent* block (one
constant colour for the 16 texels), fully transparent. The badge is drawn in that band
with void-extent blocks too, one colour per 4x4 block, so no ASTC encoder is needed:
the letters are 5x7 pixel glyphs drawn 2x2 blocks per pixel (8x8 texels), with a dark
outline. Only blocks that are still the exact transparent block are written, at the
same place in the file: the texture keeps its size and every other byte.
"""
import struct

TITLE_BNTX = 'UI/Layout2Archive/Title.Product.100.Nin_Ounce_NVN2.bntx.zs'
LOGO_PREFIX, LOGO_SUFFIX = 'Logo_', '_00'
ASTC_4X4_SRGB = 0x2D06
BLOCK = 16                          # bytes per ASTC block (4x4 texels)
# Void-extent header (no extent: the 4x13 coordinate bits all ones), then RGBA16.
VOID_HEADER = bytes.fromhex('fcfdffffffffffff')
TRANSPARENT = VOID_HEADER + bytes.fromhex('ffffffffffff0000')
BAND_ROWS = 16                      # empty block rows at the bottom of the logo
RIGHT_EDGE = 397                    # last block column of the logo artwork
GOLD = (242, 194, 58, 255)
WHITE = (255, 255, 255, 255)
OUTLINE = (26, 18, 6, 210)

GLYPHS = {
    'R': ('11110', '10001', '10001', '11110', '10100', '10010', '10001'),
    'A': ('01110', '10001', '10001', '11111', '10001', '10001', '10001'),
    'N': ('10001', '11001', '10101', '10011', '10001', '10001', '10001'),
    'D': ('11110', '10001', '10001', '10001', '10001', '10001', '11110'),
    'O': ('01110', '10001', '10001', '10001', '10001', '10001', '01110'),
    'M': ('10001', '11011', '10101', '10101', '10001', '10001', '10001'),
    'I': ('111', '010', '010', '010', '010', '010', '111'),
    'Z': ('11111', '00001', '00010', '00100', '01000', '10000', '11111'),
    'E': ('11111', '10000', '10000', '11110', '10000', '10000', '11111'),
}
WORD = 'RANDOMIZER'


def void_block(rgba):
    """ASTC void-extent block of one colour (8-bit sRGB values stored as UNORM16)."""
    return VOID_HEADER + struct.pack('<4H', *(c * 257 for c in rgba))


def badge_blocks():
    """{(column, row): rgba} of the badge in a 16-row band, left column 0."""
    height = BAND_ROWS - 2          # one outline row above and below
    cells = {}
    # Triforce: a triangle 16 blocks wide, 14 high, without its inverted middle.
    for row in range(height):
        for col in range(16):
            x, y = col + 0.5, row + 0.5
            inside = abs(x - 8) <= y * 8 / height
            middle = y >= height / 2 and abs(x - 8) <= (height - y) * 8 / height
            if inside and not middle:
                cells[(col, row + 1)] = GOLD
    # The word, 2x2 blocks per glyph pixel.
    left = 16 + 3
    for letter in WORD:
        glyph = GLYPHS[letter]
        for gy, line in enumerate(glyph):
            for gx, bit in enumerate(line):
                if bit == '1':
                    for dx in (0, 1):
                        for dy in (0, 1):
                            cells[(left + 2 * gx + dx, 1 + 2 * gy + dy)] = WHITE
        left += 2 * len(glyph[0]) + 2
    # Dark outline around everything.
    outline = {}
    for (col, row) in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                around = (col + dx, row + dy)
                if around not in cells and 0 <= around[1] < BAND_ROWS:
                    outline[around] = OUTLINE
    shift = -min(col for col, _ in outline)
    return {(col + shift, row): rgba for (col, row), rgba in {**outline, **cells}.items()}


def textures(raw):
    """(name, format, width, height, block height log2, data offset, data size) of a BNTX."""
    if raw[:4] != b'BNTX':
        raise ValueError('Not a BNTX texture archive.')
    count = struct.unpack_from('<I', raw, 0x24)[0]
    info = struct.unpack_from('<q', raw, 0x28)[0]
    for index in range(count):
        brti = struct.unpack_from('<q', raw, info + 8 * index)[0]
        if raw[brti:brti + 4] != b'BRTI':
            raise ValueError('Unexpected BNTX texture header.')
        fmt, _, width, height, _, _, block_height = struct.unpack_from('<IIiiiii', raw, brti + 0x1C)
        size = struct.unpack_from('<I', raw, brti + 0x50)[0]
        name_at, _, mips_at = struct.unpack_from('<qqq', raw, brti + 0x60)
        length = struct.unpack_from('<H', raw, name_at)[0]
        name = raw[name_at + 2:name_at + 2 + length].decode('ascii')
        yield name, fmt, width, height, block_height, struct.unpack_from('<q', raw, mips_at)[0], size


def block_offset(col, row, width_blocks, block_height):
    """Byte offset of block (col, row) in a Tegra block-linear surface of 16-byte blocks."""
    gobs_wide = (width_blocks * BLOCK + 63) // 64
    rows = 8 << block_height
    x = col * BLOCK
    gob = ((row // rows) * 512 * (1 << block_height) * gobs_wide + (x // 64) * 512 * (1 << block_height)
           + ((row % rows) // 8) * 512)
    xi, yi = x % 64, row % 8
    return gob + (xi // 32) * 256 + (yi // 2) * 64 + ((xi % 32) // 16) * 32 + (yi % 2) * 16 + (xi % 16)


def add_title_badge(raw):
    """Draw the badge on every regional title logo. Returns (bytes, report)."""
    data = bytearray(raw)
    cells = badge_blocks()
    width = max(col for col, _ in cells) + 1
    report = {}
    for name, fmt, w, h, block_height, start, size in textures(raw):
        if not (name.startswith(LOGO_PREFIX) and name.endswith(LOGO_SUFFIX) and name.count('_') == 2):
            continue
        if fmt != ASTC_4X4_SRGB:
            raise ValueError(f'{name}: unexpected texture format {fmt:#x}.')
        cols, rows = (w + 3) // 4, (h + 3) // 4
        left, top = RIGHT_EDGE + 1 - width, rows - BAND_ROWS
        if left < 0:
            raise ValueError(f'{name}: logo too narrow for the badge.')
        offsets = {}
        for row in range(top, rows):          # the whole band must still be empty
            for col in range(left, left + width):
                at = start + block_offset(col, row, cols, block_height)
                if at + BLOCK > start + size or bytes(data[at:at + BLOCK]) != TRANSPARENT:
                    raise ValueError(f'{name}: the band under the logo is not empty.')
                offsets[(col - left, row - top)] = at
        for cell, rgba in cells.items():
            at = offsets[cell]
            data[at:at + BLOCK] = void_block(rgba)
        report[name] = len(cells)
    if not report:
        raise ValueError('No title logo found.')
    return bytes(data), report
