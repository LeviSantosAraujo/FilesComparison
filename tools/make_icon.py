"""Generate icon.png for Files Comparison — pure stdlib, no dependencies.

Design: dark rounded tile with two clean "pane" columns; the left shows a
removed (red) line, the right an added (green) line.
Run: python3 tools/make_icon.py
"""

import struct
import zlib
from pathlib import Path

SIZE = 64
RADIUS = 14

BG = (31, 35, 46, 255)          # dark slate
PANE = (238, 241, 246, 255)     # light pane
ADDED = (63, 185, 110, 255)
REMOVED = (238, 100, 100, 255)
MUTED = (160, 170, 185, 255)


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


def main():
    px = [[(0, 0, 0, 0)] * SIZE for _ in range(SIZE)]

    def rect(x0, y0, x1, y1, color, radius=0):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if in_rounded(x, y, x0, y0, x1, y1, radius):
                    px[y][x] = color

    # tile
    for y in range(SIZE):
        for x in range(SIZE):
            if in_rounded(x, y, 0, 0, SIZE - 1, SIZE - 1, RADIUS):
                px[y][x] = BG

    # two light panes
    rect(10, 14, 29, 50, PANE, radius=4)
    rect(35, 14, 54, 50, PANE, radius=4)

    # left pane: muted line + removed line
    rect(14, 20, 25, 23, MUTED, radius=1)
    rect(14, 30, 25, 33, REMOVED, radius=1)

    # right pane: muted line + added line
    rect(39, 20, 50, 23, MUTED, radius=1)
    rect(39, 30, 50, 33, ADDED, radius=1)

    out = Path(__file__).resolve().parent.parent / "icon.png"
    write_png(out, SIZE, SIZE, px)
    print("wrote", out)


if __name__ == "__main__":
    main()
