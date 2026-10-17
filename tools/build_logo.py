#!/usr/bin/env python3
"""Build a custom MTK logo partition image for the Redmi Note 2 (hermes).

The logo partition (8 MiB) holds a 512-byte MTK header followed by a table:
    u32 count, u32 total_size, u32 offset[count], then zlib-compressed
    raw images (1080x1920 BGRA for full-screen ones).
Image #2 is the first boot screen shown by the bootloader (lk) and #38 the
same picture shown again by the kernel; #1 is the power-off charging
background.

The bootloader only reads a limited amount of the partition: a 4.8 MB build
showed a black screen. Keep the total at or below the stock size (~1.85 MB)
by reducing colours (--colors) and blackening #1.

usage: build_logo.py STOCK_LOGO.img PICTURE.png OUT.img [--colors 64] [--keep-charging-bg]
needs: ffmpeg on PATH
"""
import argparse
import struct
import subprocess
import sys
import tempfile
import zlib

W, H = 1080, 1920
PART_SIZE = 8 * 1024 * 1024


def picture_to_bgra(path, colors):
    vf = f"scale={W}:{H}:flags=lanczos"
    if colors:
        vf += (f",split[a][b];[a]palettegen=max_colors={colors}:reserve_transparent=0:stats_mode=full[p];"
               "[b][p]paletteuse=dither=none")
    with tempfile.NamedTemporaryFile(suffix=".png") as q:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vf", vf, q.name], check=True)
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", q.name, "-f", "rawvideo",
                              "-pix_fmt", "bgra", "-"], check=True, capture_output=True).stdout
    raw = bytearray(raw)
    assert len(raw) == W * H * 4, len(raw)
    raw[3::4] = b"\xff" * (W * H)  # stock images are fully opaque
    return bytes(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stock")
    ap.add_argument("picture")
    ap.add_argument("out")
    ap.add_argument("--colors", type=int, default=64, help="palette size, 0 = full colour")
    ap.add_argument("--keep-charging-bg", action="store_true", help="keep stock image #1")
    a = ap.parse_args()

    d = open(a.stock, "rb").read()
    magic, size = struct.unpack("<II", d[:8])
    if magic != 0x58881688 or d[8:12] != b"LOGO":
        sys.exit("not an MTK logo partition image")
    hdr, body = bytearray(d[:512]), d[512:512 + size]
    n, total = struct.unpack("<II", body[:8])
    offs = list(struct.unpack(f"<{n}I", body[8:8 + 4 * n])) + [total]
    imgs = [body[offs[i]:offs[i + 1]] for i in range(n)]

    logo = zlib.compress(picture_to_bgra(a.picture, a.colors), 9)
    imgs[2] = imgs[38] = logo  # stored twice: lk derives lengths from consecutive offsets
    if not a.keep_charging_bg:
        imgs[1] = zlib.compress(bytes([0, 0, 0, 255]) * (W * H), 9)

    pos, new_offs = 8 + 4 * n, []
    for c in imgs:
        new_offs.append(pos)
        pos += len(c)
    new_body = struct.pack("<II", n, pos) + struct.pack(f"<{n}I", *new_offs) + b"".join(imgs)
    struct.pack_into("<I", hdr, 4, len(new_body))
    out = bytes(hdr) + new_body
    out += b"\0" * (PART_SIZE - len(out))
    open(a.out, "wb").write(out)

    print(f"picture: {len(logo):,} B compressed ({a.colors or 'full'} colours)")
    print(f"logo body: {len(new_body):,} B (stock {size:,} B) -> "
          + ("OK, within stock size" if len(new_body) <= size else "WARNING: larger than stock, may show black"))


if __name__ == "__main__":
    main()
