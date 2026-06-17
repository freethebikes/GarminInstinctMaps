#!/usr/bin/env python3
"""
Generate the CrudeMaps launcher icon at each device's required size.

Connect IQ picks assets from `resources-<deviceId>/` over `resources/`, so we
write a correctly-sized icon (+ a drawables.xml referencing it) per device whose
launcher size differs from the 62x62 default.
"""

import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# size -> default goes in resources/, others in resources-<device>/
DEFAULT_SIZE = 62
DEVICE_SIZES = {
    "instinct2s": 54,
    "instincte40mm": 52,
    "instinctcrossover": 26,
}

WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)


def render(size):
    px = [[BLACK for _ in range(size)] for _ in range(size)]

    def setpx(x, y, c):
        if 0 <= x < size and 0 <= y < size:
            px[y][x] = c

    thick = max(1, size // 30)

    def line(x0, y0, x1, y1):
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(steps + 1):
            t = i / steps
            x = round(x0 + (x1 - x0) * t)
            y = round(y0 + (y1 - y0) * t)
            for dx in range(-thick, thick + 1):
                for dy in range(-thick, thick + 1):
                    setpx(x + dx, y + dy, WHITE)

    # wavy coastline across the middle
    amp = size * 0.22
    pts = [(i, int(size / 2 + amp * math.sin(i / (size / 9.0)))) for i in range(size)]
    for a, b in zip(pts, pts[1:]):
        line(a[0], a[1], b[0], b[1])

    # location dot upper-right
    cx, cy, r = int(size * 0.68), int(size * 0.32), max(2, size // 8)
    for x in range(size):
        for y in range(size):
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if d2 <= r * r:
                setpx(x, y, WHITE)
            if d2 <= (r // 3) ** 2:
                setpx(x, y, BLACK)
    return px


def write_png(px, path):
    size = len(px)
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            raw.extend(px[y][x])

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    print(f"  wrote {path} ({size}x{size})")


DRAWABLES_XML = ('<drawables>\n'
                 '    <bitmap id="LauncherIcon" filename="launcher_icon.png" />\n'
                 '</drawables>\n')


def main():
    write_png(render(DEFAULT_SIZE),
              os.path.join(ROOT, "resources", "drawables", "launcher_icon.png"))
    for dev, size in DEVICE_SIZES.items():
        base = os.path.join(ROOT, "resources-" + dev, "drawables")
        write_png(render(size), os.path.join(base, "launcher_icon.png"))
        with open(os.path.join(base, "drawables.xml"), "w") as f:
            f.write(DRAWABLES_XML)
    print("Done.")


if __name__ == "__main__":
    main()
