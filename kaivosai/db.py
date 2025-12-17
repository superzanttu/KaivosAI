"""Database layer for KaivosAI.

Provides connection helpers and CRUD for `game_objects`.
"""
from typing import Optional, Tuple
import sqlite3
from pathlib import Path

Position = Tuple[int, int]

GAME_DB = Path(__file__).parent.parent / "game.db"


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

    if vals['id'] is not None:
        cur = conn.execute("SELECT id, type, x, y FROM game_objects WHERE id = ?", (vals['id'],))
        row = cur.fetchone()
        if row:
            if row['type'] == vals['type']:
                conn.execute(
                    "UPDATE game_objects SET type = :type, name = :name, x = :x, y = :y, capacity = :capacity, stored = :stored, durability = :durability, bank = :bank, inventory = :inventory WHERE id = :id",
                    vals,
                )
                conn.commit()
                return

    if vals['x'] is not None and vals['y'] is not None:
        conn.execute("DELETE FROM game_objects WHERE x = ? AND y = ?", (vals['x'], vals['y']))
    cur = conn.execute(
        "INSERT INTO game_objects (type, name, x, y, capacity, stored, durability, bank, inventory) VALUES (:type, :name, :x, :y, :capacity, :stored, :durability, :bank, :inventory)",
        vals,
    )
    conn.commit()
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
    return cur.fetchall()
