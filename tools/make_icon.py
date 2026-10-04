"""Generate icon.png for Files Comparison — pure stdlib, no dependencies.

Design: dark rounded tile with two diff "panes"; left column shows
removed/changed lines, right column shows added/changed lines.
Run: python3 tools/make_icon.py
"""

import struct
import zlib
from pathlib import Path

SIZE = 64
RADIUS = 14

BG = (31, 35, 46, 255)          # dark slate
DIVIDER = (10, 12, 16, 255)
EQUAL = (140, 150, 165, 255)
ADDED = (63, 185, 110, 255)
REMOVED = (238, 100, 100, 255)
CHANGED = (240, 190, 80, 255)


def write_png(path: Path, w: int, h: int, pixels):
    def chunk(tag, data):
        c = tag + data
        return (struct.pack(">I", len(data)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + b"".join(bytes(px) for px in row) for row in pixels)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b""))


def rounded_rect_mask(x, y):
    """True if pixel (x,y) is inside the rounded-square tile."""
    for cx in (RADIUS, SIZE - 1 - RADIUS):
        for cy in (RADIUS, SIZE - 1 - RADIUS):
            pass
    # corners
    corners = [(RADIUS, RADIUS), (SIZE - 1 - RADIUS, RADIUS),
               (RADIUS, SIZE - 1 - RADIUS), (SIZE - 1 - RADIUS, SIZE - 1 - RADIUS)]
    for cx, cy in corners:
        in_corner_region = ((x < RADIUS) == (cx == RADIUS)
                            and (y < RADIUS) == (cy == RADIUS)
                            and x != cx and y != cy)
        if in_corner_region and x != 0:
            dx, dy = abs(x - cx), abs(y - cy)
            if dx * dx + dy * dy > RADIUS * RADIUS:
                return False
    return True


def main():
    px = [[(0, 0, 0, 0)] * SIZE for _ in range(SIZE)]

    def rect(x0, y0, x1, y1, color):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px[y][x] = color

    # tile background
    for y in range(SIZE):
        for x in range(SIZE):
            if rounded_rect_mask(x, y):
                px[y][x] = BG

    # center divider
    rect(SIZE // 2 - 1, 12, SIZE // 2, SIZE - 13, DIVIDER)

    # left pane: equal / removed lines
    left_rows = [(15, 26, EQUAL), (22, 26, REMOVED), (29, 26, CHANGED),
                 (36, 26, EQUAL), (43, 26, REMOVED), (50, 26, EQUAL)]
    for top, right, color in left_rows:
        rect(9, top, right, top + 3, color)

    # right pane: equal / added lines
    right_rows = [(15, 26, EQUAL), (22, 26, CHANGED), (29, 26, ADDED),
                  (36, 26, EQUAL), (43, 26, ADDED), (50, 26, EQUAL)]
    for top, right, color in right_rows:
        rect(SIZE - 1 - right, top, SIZE - 10, top + 3, color)

    out = Path(__file__).resolve().parent.parent / "icon.png"
    write_png(out, SIZE, SIZE, px)
    print("wrote", out)


if __name__ == "__main__":
    main()
