#!/usr/bin/env python3
"""KaivosAI game objects: Robot, Mine, Storage, Base.

This module provides simple in-memory classes suitable for a mining game.
They are intentionally minimal and designed to be extended.
"""
from dataclasses import dataclass, field
from typing import Tuple, Dict, Optional
import sqlite3
from pathlib import Path


Position = Tuple[int, int]

# SQLite DB for game state
GAME_DB = Path(__file__).parent / "game.db"


def get_game_conn(path: Optional[Path] = None):
    p = path or GAME_DB
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def init_game_db(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS game_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            name TEXT,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            capacity INTEGER,
            stored INTEGER,
            durability INTEGER,
            bank INTEGER,
            inventory INTEGER
        )
        """
    )
    conn.commit()


def persist_object(conn: sqlite3.Connection, obj):
    # map object fields to columns; use None where not applicable
    obj_type = type(obj).__name__.lower()
    vals = {
        'id': getattr(obj, 'id', None),
        'type': obj_type,
        'name': getattr(obj, 'name', None),
        'x': getattr(obj, 'pos')[0] if hasattr(obj, 'pos') else None,
        'y': getattr(obj, 'pos')[1] if hasattr(obj, 'pos') else None,
        'capacity': getattr(obj, 'capacity', None),
        'stored': getattr(obj, 'stored', None),
        'durability': getattr(obj, 'durability', None),
        'bank': getattr(obj, 'bank', None),
        'inventory': getattr(obj, 'inventory', None),
    }
    # If object already has an id and exists in DB, update the row
    if vals['id'] is not None:
        cur = conn.execute("SELECT id, type, x, y FROM game_objects WHERE id = ?", (vals['id'],))
        row = cur.fetchone()
        if row:
            # If the existing DB row appears to be the same object (same type), update it.
            # If types differ, treat this as a request to create a new object (ignore provided id)
            if row['type'] == vals['type']:
                conn.execute(
                    "UPDATE game_objects SET type = :type, name = :name, x = :x, y = :y, capacity = :capacity, stored = :stored, durability = :durability, bank = :bank, inventory = :inventory WHERE id = :id",
                    vals,
                )
                conn.commit()
                return

    # New object: remove any existing row at same coordinates, then INSERT
    if vals['x'] is not None and vals['y'] is not None:
        conn.execute("DELETE FROM game_objects WHERE x = ? AND y = ?", (vals['x'], vals['y']))
    cur = conn.execute(
        "INSERT INTO game_objects (type, name, x, y, capacity, stored, durability, bank, inventory) VALUES (:type, :name, :x, :y, :capacity, :stored, :durability, :bank, :inventory)",
        vals,
    )
    conn.commit()
    # assign generated id back to object if possible
    new_id = cur.lastrowid
    try:
        setattr(obj, 'id', new_id)
    except Exception:
        pass


def delete_object_db(conn: sqlite3.Connection, pos: Position):
    x, y = pos
    conn.execute("DELETE FROM game_objects WHERE x = ? AND y = ?", (x, y))
    conn.commit()


def load_objects_from_db(conn: sqlite3.Connection):
    cur = conn.execute("SELECT * FROM game_objects")
    rows = cur.fetchall()
    objs = []
    for r in rows:
        t = r['type']
        kwargs = {'pos': (r['x'], r['y'])}
        if t == 'robot':
            o = Robot(id=r['id'], pos=kwargs['pos'], capacity=r['capacity'] or 10)
            o.inventory = r['inventory'] or 0
        elif t == 'mine':
            o = Mine(id=r['id'], name=r['name'] or 'Mine', pos=kwargs['pos'], durability=r['durability'] or 0)
        elif t == 'storage':
            o = Storage(id=r['id'], name=r['name'] or 'Storage', pos=kwargs['pos'], capacity=r['capacity'] or 100)
            o.stored = r['stored'] or 0
        elif t == 'base':
            o = Base(id=r['id'], name=r['name'] or 'Base', pos=kwargs['pos'])
            o.bank = r['bank'] or 0
        elif t == 'rock':
            o = Rock(id=r['id'], name=r['name'] or 'Rock', pos=kwargs['pos'])
        else:
            continue
        objs.append(o)
    return objs


@dataclass
class Building:
    id: Optional[int] = None
    name: str = ""
    pos: Position = (0, 0)


@dataclass
class Mine(Building):
    ore_type: str = "ore"
    durability: int = 10

    def extract(self, amount: int) -> int:
        """Extract up to `amount` units from the mine.

        Mines have a simple durability which decreases as resources are
        extracted. When durability reaches 0, the mine is exhausted.
        Returns the actual amount extracted.
        """
        if self.durability <= 0:
            return 0
        taken = min(amount, self.durability)
        self.durability -= taken
        return taken


@dataclass
class Storage(Building):
    capacity: int = 100
    stored: int = 0

    def store(self, amount: int) -> int:
        """Store up to `amount` units. Returns amount actually stored."""
        space = self.capacity - self.stored
        if space <= 0:
            return 0
        put = min(space, amount)
        self.stored += put
        return put

    def withdraw(self, amount: int) -> int:
        """Withdraw up to `amount` units. Returns withdrawn amount."""
        take = min(self.stored, amount)
        self.stored -= take
        return take


@dataclass
class Base(Building):
    bank: int = 0

    def deposit(self, amount: int) -> int:
        """Accept deposit into the base; returns accepted amount (all)."""
        self.bank += amount
        return amount


@dataclass
class Robot:
    id: Optional[int] = None
    pos: Position = (0, 0)
    capacity: int = 10
    inventory: int = 0

    def move_to(self, target: Position):
        self.pos = target

    def mine(self, mine: Mine, amount: int = None) -> int:
        """Mine resources from a `Mine` if at the same position.

        If `amount` is None, mine up to free capacity.
        Returns amount added to robot inventory.
        """
        if self.pos != mine.pos:
            return 0
        free = self.capacity - self.inventory
        if free <= 0:
            return 0
        want = free if amount is None else min(free, amount)
        taken = mine.extract(want)
        self.inventory += taken
        return taken

    def deposit_to_storage(self, storage: Storage) -> int:
        """Deposit as much as possible from inventory into `Storage`.
        Returns amount deposited.
        """
        if self.pos != storage.pos:
            return 0
        deposited = storage.store(self.inventory)
        self.inventory -= deposited
        return deposited

    def deposit_to_base(self, base: Base) -> int:
        """Deposit all inventory to `Base`; returns amount deposited."""
        if self.pos != base.pos:
            return 0
        amount = self.inventory
        accepted = base.deposit(amount)
        self.inventory -= accepted
        return accepted


@dataclass
class Rock(Building):
    """Impassable obstacle; robots cannot occupy a cell with a Rock."""
    pass


class Map:
    """A simple 2D map for KaivosAI.

    - Size is `width` x `height` (default 100x100).
    - Each cell can contain at most one object: `Robot`, `Mine`, `Storage`, `Base`, or `Rock`.
    """

    def __init__(self, width: int = 100, height: int = 100, conn: Optional[sqlite3.Connection] = None):
        self.width = width
        self.height = height
        # optional DB connection for persistence
        self.conn = conn
        # store objects by (x,y) -> object
        self.cells: Dict[Position, object] = {}
        # if a DB connection is provided, ensure schema and load existing objects
        if self.conn:
            init_game_db(self.conn)
            objs = load_objects_from_db(self.conn)
            for o in objs:
                self.cells[o.pos] = o

    def in_bounds(self, pos: Position) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_occupied(self, pos: Position) -> bool:
        return pos in self.cells

    def get(self, pos: Position):
        return self.cells.get(pos)
    def add_object(self, obj, pos: Position):
        """Place `obj` at `pos`.

        Raises ValueError for out-of-bounds or occupied cells.
        """
        if not self.in_bounds(pos):
            raise ValueError("Position out of bounds")
        if self.is_occupied(pos):
            raise ValueError("Cell is already occupied")
        if hasattr(obj, 'pos'):
            obj.pos = pos
        self.cells[pos] = obj
        if self.conn:
            persist_object(self.conn, obj)
        return True

    def remove_object(self, pos: Position):
        """Remove and return object at `pos`. Returns None if empty."""
        obj = self.cells.pop(pos, None)
        if obj and self.conn:
            delete_object_db(self.conn, pos)
        return obj

    def move_object(self, from_pos: Position, to_pos: Position):
        """Move object from `from_pos` to `to_pos` with basic checks.

        Raises ValueError on invalid moves.
        """
        if not self.in_bounds(from_pos) or not self.in_bounds(to_pos):
            raise ValueError("Position out of bounds")
        if from_pos not in self.cells:
            raise ValueError("No object at source position")
        if to_pos in self.cells:
            raise ValueError("Destination occupied")
        obj = self.cells.pop(from_pos)
        if hasattr(obj, 'pos'):
            obj.pos = to_pos
        self.cells[to_pos] = obj
        if self.conn:
            persist_object(self.conn, obj)
        return True


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
        # cap size for readability
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
            # support both: add TYPE ID X Y  and  add TYPE X Y
            try:
                if len(args) == 3:
                    oid = None
                    x = int(args[1]); y = int(args[2])
                else:
                    # len >=4
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
                # auto bounds from objects
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
    # Demo: show map operations and then enter REPL
    conn = get_game_conn()
    init_game_db(conn)
    game_map = Map(width=50, height=50, conn=conn)
    mine = Mine(id=1, name="Iron Mine", pos=(0, 0), durability=25)
    storage = Storage(id=2, name="Storage A", pos=(1, 0), capacity=50)
    base = Base(id=3, name="Base", pos=(2, 0))
    bot = Robot(id=1, pos=(0, 1), capacity=5)
    rock = Rock(id=99, name="Boulder", pos=(1, 1))

    # place buildings and rock on the map (remove any existing objects at those positions first)
    for obj in (mine, storage, base, rock, bot):
        # remove existing object at position (also removes from DB if using persistence)
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

