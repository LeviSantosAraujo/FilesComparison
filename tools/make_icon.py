"""Generate icon.png for Files Comparison — pure stdlib, no dependencies.

Design: a dark rounded tile holding a light document page (folded corner,
a few text lines) with a magnifying glass over it — "a file being searched".
Run: python3 tools/make_icon.py
"""

import math
import struct
import zlib
from pathlib import Path

SIZE = 64
RADIUS = 14

BG = (31, 35, 46, 255)          # dark slate tile
PANE = (240, 243, 248, 255)     # document page
FOLD = (190, 198, 212, 255)     # folded corner
MUTED = (150, 160, 175, 255)    # text lines
GLASS = (47, 109, 246, 255)     # magnifier (accent blue)


def write_png(path: Path, w: int, h: int, pixels):
    def chunk(tag, data):
        c = tag + data
        return (struct.pack(">I", len(data)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in pixels)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b""))


def in_rounded(x, y, x0, y0, x1, y1, r):
    """True if pixel (x,y) is inside rounded rect [x0..x1] x [y0..y1]."""
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    corners = []
    if x < x0 + r and y < y0 + r:
        corners.append((x0 + r, y0 + r))
    if x > x1 - r and y < y0 + r:
        corners.append((x1 - r, y0 + r))
    if x < x0 + r and y > y1 - r:
        corners.append((x0 + r, y1 - r))
    if x > x1 - r and y > y1 - r:
        corners.append((x1 - r, y1 - r))
    return all((x - cx) ** 2 + (y - cy) ** 2 <= r * r for cx, cy in corners)


def _seg_dist(x, y, x0, y0, x1, y1):
    """Distance from point to segment."""
    dx, dy = x1 - x0, y1 - y0
    if dx == dy == 0:
        return math.hypot(x - x0, y - y0)
    t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x0 + t * dx), y - (y0 + t * dy))


def main():
    px = [[(0, 0, 0, 0)] * SIZE for _ in range(SIZE)]

    def paint(color, pred):
        for y in range(SIZE):
            for x in range(SIZE):
                if pred(x, y):
                    px[y][x] = color

    # tile
    paint(BG, lambda x, y: in_rounded(x, y, 0, 0, SIZE - 1, SIZE - 1, RADIUS))

    # document page with the top-right corner folded over
    fold = 9
    in_fold = lambda x, y: (x >= 44 - fold and y <= 8 + fold and x <= 44
                            and y >= 8
                            and (x - (44 - fold)) + (8 + fold - y) <= fold)
    paint(PANE, lambda x, y:
          in_rounded(x, y, 14, 8, 44, 50, 3) and not in_fold(x, y))
    paint(FOLD, in_fold)
    # text lines on the page
    paint(MUTED, lambda x, y:
          18 <= x <= 36 and ((18 <= y <= 20) or (24 <= y <= 26) or (30 <= y <= 32)))
    paint(MUTED, lambda x, y: 18 <= x <= 30 and 36 <= y <= 38)

    # magnifying glass over the page's lower-right
    cx, cy, r_out, r_in = 39, 37, 12, 8.5
    paint(GLASS, lambda x, y:
          r_in <= math.hypot(x - cx, y - cy) <= r_out)
    # lens interior: subtle tint
    paint((120, 160, 250, 160), lambda x, y: math.hypot(x - cx, y - cy) < r_in)
    # handle
    hx0, hy0 = cx + r_out - 3, cy + r_out - 3
    paint(GLASS, lambda x, y: _seg_dist(x, y, hx0, hy0, 55, 55) <= 3)

    out = Path(__file__).resolve().parent.parent / "icon.png"
    write_png(out, SIZE, SIZE, px)
    print("wrote", out)


if __name__ == "__main__":
    main()
