#!/usr/bin/env python3
"""Realtime ASCII map viewer for KaivosAI.

Polls `game.db` and renders a region of the map periodically. Can run
concurrently with `kaivosai.py` because it reads the SQLite DB directly.
"""
import time
import argparse
import os
from pathlib import Path

import kaivosai


def clear_screen():
    print("\x1b[H\x1b[2J", end="")


def render(objects, minx, maxx, miny, maxy):
    w = maxx - minx + 1
    h = maxy - miny + 1
    if w <= 0 or h <= 0:
        print("Empty region")
        return
    if w > 160 or h > 80:
        print(f"Region too large ({w}x{h})")
        return
    grid = [["." for _ in range(w)] for __ in range(h)]
    for o in objects:
        x, y = o.pos
        if x < minx or x > maxx or y < miny or y > maxy:
            continue
        ch = "?"
        if isinstance(o, kaivosai.Robot):
            ch = "R"
        elif isinstance(o, kaivosai.Mine):
            ch = "M"
        elif isinstance(o, kaivosai.Storage):
            ch = "S"
        elif isinstance(o, kaivosai.Base):
            ch = "B"
        elif isinstance(o, kaivosai.Rock):
            ch = "#"
        grid[y - miny][x - minx] = ch
    # print column header (x coordinates modulo 10) and rows with y coords
    # column header spacer for y labels
    col_labels = ' '.join(str(x % 10) for x in range(minx, maxx + 1))
    print('   ' + col_labels)
    # Print rows with y ascending so y=0 appears at top (top-left origin)
    for yi, row in enumerate(grid, start=miny):
        print(f"{yi:2d} " + ' '.join(row))


def compute_auto_bounds(objects, width, height, padding=2):
    if not objects:
        return 0, min(width - 1, 9), 0, min(height - 1, 9)
    xs = [o.pos[0] for o in objects]
    ys = [o.pos[1] for o in objects]
    minx = max(0, min(xs) - padding)
    maxx = min(width - 1, max(xs) + padding)
    miny = max(0, min(ys) - padding)
    maxy = min(height - 1, max(ys) + padding)
    return minx, maxx, miny, maxy


def main():
    p = Path(__file__).parent / "game.db"
    parser = argparse.ArgumentParser(description="KaivosAI realtime map viewer")
    parser.add_argument("--interval", type=float, default=1.0, help="Refresh interval seconds")
    parser.add_argument("--width", type=int, default=50, help="Map width to assume")
    parser.add_argument("--height", type=int, default=50, help="Map height to assume")
    parser.add_argument("--region", nargs=4, type=int, help="minx maxx miny maxy")
    args = parser.parse_args()

    conn = kaivosai.get_game_conn(p)
    # create a GameClock wrapper (reads/writes small meta keys); do not start it
    try:
        clock = kaivosai.GameClock(conn)
    except Exception:
        clock = None
    try:
        while True:
            rows = kaivosai.load_objects_from_db(conn)
            # convert DB rows into model objects for rendering
            objs = []
            for r in rows:
                try:
                    obj = kaivosai.create_object(r['type'], id=r['id'], name=r['name'], pos=(r['x'], r['y']), capacity=r['capacity'], durability=r['durability'])
                except Exception:
                    # fallback: create a simple object with pos attribute
                    class Simple:
                        def __init__(self, pos):
                            self.pos = pos
                    obj = Simple((r['x'], r['y']))
                objs.append(obj)
            if args.region:
                minx, maxx, miny, maxy = args.region
            else:
                minx, maxx, miny, maxy = compute_auto_bounds(objs, args.width, args.height)
            clear_screen()
            # clock display: hh:mm:ss with blinking colons (visible on even seconds)
            if clock:
                try:
                    sec = clock.seconds
                    hh = (sec % 86400) // 3600
                    mm = (sec % 3600) // 60
                    ss = sec % 60
                    colon = ':' if (ss % 2) == 0 else ' '
                    clock_str = f"{hh:02d}{colon}{mm:02d}{colon}{ss:02d}"
                except Exception:
                    clock_str = "--:--:--"
            else:
                clock_str = "--:--:--"

            print(f"KaivosAI Map Viewer — {len(objs)} objects — {clock_str} — refresh {args.interval}s")
            print(f"Region: x={minx}..{maxx} y={miny}..{maxy}")
            render(objs, minx, maxx, miny, maxy)
            print("\nLegend: R=Robot, M=Mine, S=Storage, B=Base, #=Rock")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nExiting viewer")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
