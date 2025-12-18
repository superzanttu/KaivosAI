from typing import Tuple, Dict, Optional
import sqlite3

from .db import init_game_db, persist_object, delete_object_db, load_objects_from_db
from .models import Robot, Mine, Storage, Base, Rock

Position = Tuple[int, int]


class Map:
    def __init__(self, width: int = 100, height: int = 100, conn: Optional[sqlite3.Connection] = None):
        self.width = width
        self.height = height
        self.conn = conn
        self.cells: Dict[Position, object] = {}
        if self.conn:
            init_game_db(self.conn)
            rows = load_objects_from_db(self.conn)
            # loader returns sqlite rows; convert to model instances
            from .models import create_object
            for r in rows:
                t = r['type']
                pos = (r['x'], r['y'])
                obj = create_object(t, id=r['id'], name=r['name'], pos=pos, capacity=r['capacity'], durability=r['durability'])
                # set extra fields
                if isinstance(obj, Storage):
                    obj.stored = r['stored'] or 0
                if isinstance(obj, Base):
                    obj.bank = r['bank'] or 0
                if isinstance(obj, Robot):
                    obj.inventory = r['inventory'] or 0
                self.cells[pos] = obj

    def in_bounds(self, pos: Position) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_occupied(self, pos: Position) -> bool:
        return pos in self.cells

    def get(self, pos: Position):
        return self.cells.get(pos)

    def add_object(self, obj, pos: Position):
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

    def remove_object(self, pos_or_id):
        """Remove by position tuple `(x,y)` or by integer `id`.

        Returns the removed object or None if not found.
        """
        # Remove by position
        if isinstance(pos_or_id, tuple):
            pos = pos_or_id
            obj = self.cells.pop(pos, None)
            if obj and self.conn:
                delete_object_db(self.conn, pos)
            return obj

        # Remove by id
        try:
            oid = int(pos_or_id)
        except Exception:
            return None

        # Try to find object in in-memory cells
        found_pos = None
        for p, o in list(self.cells.items()):
            if getattr(o, 'id', None) == oid:
                found_pos = p
                break

        if found_pos is not None:
            obj = self.cells.pop(found_pos)
            if self.conn:
                delete_object_db(self.conn, found_pos)
            return obj

        # If not in memory, try to remove from DB (and return None)
        if self.conn:
            cur = self.conn.execute("SELECT x,y FROM game_objects WHERE id = ?", (oid,))
            row = cur.fetchone()
            if row:
                pos = (row['x'], row['y'])
                obj = self.cells.pop(pos, None)
                delete_object_db(self.conn, pos)
                return obj

        return None

    def move_object(self, from_pos: Position, to_pos: Position):
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
