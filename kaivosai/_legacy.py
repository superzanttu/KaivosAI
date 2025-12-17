#!/usr/bin/env python3
"""Legacy single-file implementation of KaivosAI.

This file is an exact copy of the previous `kaivosai.py` and is used
to provide a stable API while the codebase is refactored into smaller
modules.
"""
from dataclasses import dataclass, field
from typing import Tuple, Dict, Optional
import sqlite3
from pathlib import Path


Position = Tuple[int, int]

# SQLite DB for game state
GAME_DB = Path(__file__).parent.parent / "game.db"

from .db import get_game_conn, init_game_db
from .models import Building, Mine, Storage, Base, Robot, Rock, create_object
from .map import Map


def create_object(obj_type: str, id: Optional[int] = None, name: str = None, **kwargs):
    t = obj_type.lower()
    if t == 'robot':
        return Robot(id=id, pos=kwargs.get('pos', (0, 0)), capacity=kwargs.get('capacity', 10))
    if t == 'mine':
        return Mine(id=id, name=name or 'Mine', pos=kwargs.get('pos', (0, 0)), durability=kwargs.get('durability', 10))
    if t == 'storage':
        return Storage(id=id, name=name or 'Storage', pos=kwargs.get('pos', (0, 0)), capacity=kwargs.get('capacity', 100))
    if t == 'base':
        return Base(id=id, name=name or 'Base', pos=kwargs.get('pos', (0, 0)))
    if t == 'rock':
        return Rock(id=id, name=name or 'Rock', pos=kwargs.get('pos', (0, 0)))
    raise ValueError('Unknown object type')


def repl(game_map: Map):
    import shlex

    def show_help():
        print("Commands:")
        print("  add TYPE [ID] X Y         - add object (ID optional; omitted = auto-assigned)")
        print("  remove X Y                - remove object at position")
        print("  move X1 Y1 X2 Y2          - move object")
        print("  list                      - list all objects")
        print("  get X Y                   - show object at position")
        print("  show [minx maxx miny maxy]- show ASCII map (auto-bounds if omitted)")
        print("  help                      - show this help")
        print("  quit                      - exit")

    def ascii_map(minx, maxx, miny, maxy):
        w = maxx - minx + 1
        h = maxy - miny + 1
        if w > 80 or h > 40:
            print(f"Region too large ({w}x{h}); limit to 80x40")
            return
        rows = []
        for y in range(miny, maxy + 1):
            row = []
            for x in range(minx, maxx + 1):
                obj = game_map.get((x, y))
                if obj is None:
                    row.append('.')
                elif isinstance(obj, Robot):
                    row.append('R')
                elif isinstance(obj, Mine):
                    row.append('M')
                elif isinstance(obj, Storage):
                    row.append('S')
                elif isinstance(obj, Base):
                    row.append('B')
                elif isinstance(obj, Rock):
                    row.append('#')
                else:
                    row.append('?')
            rows.append(''.join(row))
        for r in rows:
            print(r)

    while True:
        try:
            line = input('> ')
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = []
        try:
            parts = shlex.split(line)
        except Exception:
            parts = line.split()
        if not parts:
            continue
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd in ('quit', 'exit'):
            break
        if cmd == 'help':
            show_help()
            continue
        if cmd == 'add':
            if len(args) < 3:
                print('Usage: add TYPE [ID] X Y')
                continue
            typ = args[0]
            try:
                if len(args) == 3:
                    oid = None
                    x = int(args[1]); y = int(args[2])
                else:
                    oid = int(args[1])
                    x = int(args[2]); y = int(args[3])
            except ValueError:
                print('ID,X,Y must be integers')
                continue
            try:
                obj = create_object(typ, oid, pos=(x, y))
                game_map.add_object(obj, (x, y))
                print('Added', typ, 'at', (x, y), 'id=', getattr(obj, 'id', None))
            except Exception as e:
                print('Error:', e)
            continue
        if cmd == 'remove':
            if len(args) < 2:
                print('Usage: remove X Y')
                continue
            try:
                x = int(args[0]); y = int(args[1])
            except ValueError:
                print('X,Y must be integers')
                continue
            obj = game_map.remove_object((x, y))
            print('Removed:', type(obj).__name__ if obj else 'None')
            continue
        if cmd == 'move':
            if len(args) < 4:
                print('Usage: move X1 Y1 X2 Y2')
                continue
            try:
                x1 = int(args[0]); y1 = int(args[1]); x2 = int(args[2]); y2 = int(args[3])
            except ValueError:
                print('Coordinates must be integers')
                continue
            try:
                game_map.move_object((x1, y1), (x2, y2))
                print('Moved')
            except Exception as e:
                print('Error:', e)
            continue
        if cmd == 'list':
            for p, o in sorted(game_map.cells.items()):
                print(p, type(o).__name__, getattr(o, 'id', None))
            continue
        if cmd == 'get':
            if len(args) < 2:
                print('Usage: get X Y')
                continue
            try:
                x = int(args[0]); y = int(args[1])
            except ValueError:
                print('X,Y must be integers')
                continue
            obj = game_map.get((x, y))
            print(obj if obj else 'Empty')
            continue
        if cmd == 'show':
            if len(args) == 4:
                try:
                    minx = int(args[0]); maxx = int(args[1]); miny = int(args[2]); maxy = int(args[3])
                except ValueError:
                    print('Coordinates must be integers')
                    continue
            else:
                if not game_map.cells:
                    minx = 0; miny = 0; maxx = min(game_map.width - 1, 9); maxy = min(game_map.height - 1, 9)
                else:
                    xs = [p[0] for p in game_map.cells.keys()]
                    ys = [p[1] for p in game_map.cells.keys()]
                    minx = max(0, min(xs) - 2)
                    maxx = min(game_map.width - 1, max(xs) + 2)
                    miny = max(0, min(ys) - 2)
                    maxy = min(game_map.height - 1, max(ys) + 2)
            ascii_map(minx, maxx, miny, maxy)
            continue
        print('Unknown command. Type help.')


def run_demo():
    conn = get_game_conn()
    init_game_db(conn)
    game_map = Map(width=50, height=50, conn=conn)
    mine = Mine(id=1, name="Iron Mine", pos=(0, 0), durability=25)
    storage = Storage(id=2, name="Storage A", pos=(1, 0), capacity=50)
    base = Base(id=3, name="Base", pos=(2, 0))
    bot = Robot(id=1, pos=(0, 1), capacity=5)
    rock = Rock(id=99, name="Boulder", pos=(1, 1))

    for obj in (mine, storage, base, rock, bot):
        removed = game_map.remove_object(obj.pos)
        if removed:
            print(f"Removed existing {type(removed).__name__} at {obj.pos}")
        game_map.add_object(obj, obj.pos)

    print("Map initial contents:")
    for p, o in sorted(game_map.cells.items()):
        print(p, type(o).__name__, getattr(o, 'id', None))

    print("\nEntering interactive command prompt. Type 'help' for commands.")
    try:
        repl(game_map)
    finally:
        conn.close()


if __name__ == "__main__":
    run_demo()
