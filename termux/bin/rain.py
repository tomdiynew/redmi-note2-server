#!/data/data/com.termux/files/usr/bin/python3
"""Falling green "digital rain" for N seconds (default 4), plain ANSI, no deps."""
import os
import random
import sys
import time

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
CHARS = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ$#%&*+=<>?/\\|{}[]@"
FPS = 20


def main():
    cols, rows = os.get_terminal_size()
    out = sys.stdout
    out.write("\033[?25l\033[2J\033[40m")  # hide cursor, clear, black bg
    # one drop per column: head row (float), speed, trail length
    drops = [[random.uniform(-rows, 0), random.uniform(0.6, 1.6), random.randint(6, rows)]
             for _ in range(cols)]
    end = time.monotonic() + SECONDS
    while time.monotonic() < end:
        buf = []
        for x, d in enumerate(drops):
            head = int(d[0])
            for y in (head, head - 1, head - 2):
                if 0 <= y < rows:
                    colour = "97" if y == head else ("92" if y == head - 1 else "32")
                    buf.append(f"\033[{y + 1};{x + 1}H\033[{colour}m{random.choice(CHARS)}")
            tail = head - d[2]
            if 0 <= tail < rows:
                buf.append(f"\033[{tail + 1};{x + 1}H ")
            d[0] += d[1]
            if tail >= rows:
                d[:] = [random.uniform(-rows / 2, 0), random.uniform(0.6, 1.6), random.randint(6, rows)]
        out.write("".join(buf))
        out.flush()
        time.sleep(1 / FPS)
    out.write("\033[0m\033[2J\033[H\033[?25h")
    out.flush()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write("\033[0m\033[2J\033[H\033[?25h")
