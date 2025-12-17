"""Real-time ASCII map viewer for KaivosAI.

Polls the `game.db` and renders a small ASCII viewport centered on objects.
"""
import time
import os
from typing import Tuple

from .db import get_game_conn


def auto_bounds(rows):
    xs = [r['x'] for r in rows]
    ys = [r['y'] for r in rows]
    if not xs or not ys:
        return 0, 9, 0, 9
    minx = max(0, min(xs) - 2)
    maxx = max(xs) + 2
    miny = max(0, min(ys) - 2)
    maxy = max(ys) + 2
    return minx, maxx, miny, maxy


def render(rows, minx, maxx, miny, maxy):
    w = maxx - minx + 1
    h = maxy - miny + 1
    if w > 160 or h > 80:
        print(f"Region too large ({w}x{h})")
        return
    grid = []
    mapping = {}
    for r in rows:
        mapping[(r['x'], r['y'])] = r['type'][0].upper()
    for y in range(miny, maxy + 1):
        row = ''.join(mapping.get((x, y), '.') for x in range(minx, maxx + 1))
        grid.append(row)
    print('\n'.join(grid))


def run_viewer(poll_seconds: float = 0.5):
    conn = get_game_conn()
    try:
        while True:
            rows = list(conn.execute('SELECT x,y,type FROM game_objects'))
            minx, maxx, miny, maxy = auto_bounds(rows)
            os.system('cls' if os.name == 'nt' else 'clear')
            render(rows, minx, maxx, miny, maxy)
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        print('\nViewer stopped')
    finally:
        conn.close()


if __name__ == '__main__':
    run_viewer()
