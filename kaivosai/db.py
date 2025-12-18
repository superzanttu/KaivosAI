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
            inventory INTEGER,
            UNIQUE(x,y)
        )
        """
    )
    conn.commit()


def persist_object(conn: sqlite3.Connection, obj):
    obj_type = type(obj).__name__.lower()
    vals = {
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

    # Use UPSERT keyed on coordinates so coordinates are authoritative.
    try:
        cur = conn.execute(
            """
            INSERT INTO game_objects (type, name, x, y, capacity, stored, durability, bank, inventory)
            VALUES (:type, :name, :x, :y, :capacity, :stored, :durability, :bank, :inventory)
            ON CONFLICT(x,y) DO UPDATE SET
                type=excluded.type,
                name=excluded.name,
                capacity=excluded.capacity,
                stored=excluded.stored,
                durability=excluded.durability,
                bank=excluded.bank,
                inventory=excluded.inventory
            """,
            vals,
        )
        conn.commit()

        # Retrieve the canonical id for this position and assign to object
        if vals['x'] is not None and vals['y'] is not None:
            cur2 = conn.execute("SELECT id FROM game_objects WHERE x = ? AND y = ?", (vals['x'], vals['y']))
            row = cur2.fetchone()
            if row:
                try:
                    setattr(obj, 'id', row['id'])
                except Exception:
                    pass
    except sqlite3.OperationalError as e:
        # Fallback for older DBs that don't have UNIQUE(x,y): perform delete+insert
        msg = str(e)
        if 'ON CONFLICT' in msg or 'does not match any PRIMARY KEY or UNIQUE constraint' in msg:
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
        else:
            raise


def delete_object_db(conn: sqlite3.Connection, pos: Position):
    x, y = pos
    conn.execute("DELETE FROM game_objects WHERE x = ? AND y = ?", (x, y))
    conn.commit()


def delete_object_by_id(conn: sqlite3.Connection, oid: int):
    conn.execute("DELETE FROM game_objects WHERE id = ?", (oid,))
    conn.commit()


def load_objects_from_db(conn: sqlite3.Connection):
    cur = conn.execute("SELECT * FROM game_objects")
    return cur.fetchall()
