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
    # print rows top-to-bottom (y increasing downwards)
    for row in grid:
        print("".join(row))


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
    try:
        while True:
            objs = kaivosai.load_objects_from_db(conn)
            if args.region:
                minx, maxx, miny, maxy = args.region
            else:
                minx, maxx, miny, maxy = compute_auto_bounds(objs, args.width, args.height)
            clear_screen()
            print(f"KaivosAI Map Viewer — {len(objs)} objects — refresh {args.interval}s")
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
