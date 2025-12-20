"""Database layer for KaivosAI game state persistence.

Provides SQLite connection management and CRUD operations for game_objects table.
All game state (buildings, robots, materials) is persisted to databases/game.db.

Threading:
    - Main thread (CLI/TUI) uses single connection for all operations
    - GameClock thread uses separate connection with check_same_thread=False
    - WAL mode enabled for better concurrent read performance

Schema:
    - game_objects: All physical objects (UNIQUE constraint on x,y)
    - game_meta: Key-value store for game settings and clock state
    - game_events: Event log for UI display

Example:
    >>> conn = get_game_conn()
    >>> init_game_db(conn)
    >>> robot = Robot(id=1, pos=(5,7))
    >>> persist_object(conn, robot)
"""
from typing import Optional, Tuple
import sqlite3
from pathlib import Path

Position = Tuple[int, int]

GAME_DB = Path(__file__).parent.parent / "databases" / "game.db"


def get_game_conn(path: Optional[Path] = None):
    """Create SQLite connection with WAL mode enabled.
    
    Args:
        path: Database file path (default: databases/game.db)
        
    Returns:
        sqlite3.Connection with row_factory=Row and WAL mode
        
    Note:
        Creates databases/ directory if it doesn't exist.
        Timeout set to 10 seconds to handle concurrent access.
    """
    p = path or GAME_DB
    # Ensure databases directory exists
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_game_db(conn: sqlite3.Connection):
    """Initialize database schema (idempotent - safe to call multiple times).
    
    Creates tables:
        - game_objects: Physical entities with UNIQUE(x,y) constraint
        - game_meta: Key-value store for game state
        - game_events: Event log with cleanup after 1000 entries
        
    Args:
        conn: Database connection
        
    Note:
        Uses CREATE TABLE IF NOT EXISTS - safe for existing databases.
    """
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
    # meta table for small key/value state (clock, settings)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS game_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    # events table for game events with timestamps
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS game_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            object_id INTEGER,
            object_type TEXT,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            x INTEGER,
            y INTEGER
        )
        """
    )
    # Index for faster queries by timestamp
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_timestamp 
        ON game_events(timestamp DESC)
        """
    )
    conn.commit()


def persist_object(conn: sqlite3.Connection, obj):
    """Save or update game object in database (UPSERT operation).
    
    Uses ON CONFLICT(x,y) DO UPDATE to handle position uniqueness constraint.
    Falls back to DELETE+INSERT for old databases without UNIQUE constraint.
    
    Args:
        conn: Database connection
        obj: Game object (Robot, Mine, Storage, Base, Rock)
        
    Note:
        Auto-commits the transaction.
        Position (x,y) is the natural key - only one object per cell.
        
    Example:
        >>> robot = Robot(id=1, name='Bot1', pos=(5,7), inventory=3)
        >>> persist_object(conn, robot)
    """
    obj_type = type(obj).__name__.lower()
    obj_id = getattr(obj, 'id', None)
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
    # If object has an ID, use it; otherwise let DB auto-assign
    try:
        if obj_id is not None:
            # Insert with explicit ID
            cur = conn.execute(
                """
                INSERT INTO game_objects (id, type, name, x, y, capacity, stored, durability, bank, inventory)
                VALUES (:id, :type, :name, :x, :y, :capacity, :stored, :durability, :bank, :inventory)
                ON CONFLICT(x,y) DO UPDATE SET
                    id=excluded.id,
                    type=excluded.type,
                    name=excluded.name,
                    capacity=excluded.capacity,
                    stored=excluded.stored,
                    durability=excluded.durability,
                    bank=excluded.bank,
                    inventory=excluded.inventory
                """,
                {**vals, 'id': obj_id},
            )
        else:
            # Let DB auto-assign ID
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
            if obj_id is not None:
                cur = conn.execute(
                    "INSERT INTO game_objects (id, type, name, x, y, capacity, stored, durability, bank, inventory) VALUES (:id, :type, :name, :x, :y, :capacity, :stored, :durability, :bank, :inventory)",
                    {**vals, 'id': obj_id},
                )
            else:
                cur = conn.execute(
                    "INSERT INTO game_objects (type, name, x, y, capacity, stored, durability, bank, inventory) VALUES (:type, :name, :x, :y, :capacity, :stored, :durability, :bank, :inventory)",
                    vals,
                )
            conn.commit()
            new_id = cur.lastrowid if obj_id is None else obj_id
            try:
                setattr(obj, 'id', new_id)
            except Exception:
                pass
        else:
            raise


def delete_object_db(conn: sqlite3.Connection, pos: Position):
    """Delete game object at specified position.
    
    Args:
        conn: Database connection
        pos: (x, y) coordinates of object to delete
        
    Note:
        Auto-commits the transaction.
        Silently succeeds if no object at position.
    """
    x, y = pos
    conn.execute("DELETE FROM game_objects WHERE x = ? AND y = ?", (x, y))
    conn.commit()


def delete_object_by_id(conn: sqlite3.Connection, oid: int):
    """Delete game object by ID.
    
    Args:
        conn: Database connection
        oid: Object ID to delete
        
    Note:
        Auto-commits the transaction.
        Silently succeeds if object ID doesn't exist.
    """
    conn.execute("DELETE FROM game_objects WHERE id = ?", (oid,))
    conn.commit()


def load_objects_from_db(conn: sqlite3.Connection):
    """Load all game objects from database.
    
    Args:
        conn: Database connection
        
    Returns:
        List of sqlite3.Row objects with all object fields
        
    Note:
        Returns raw database rows - use create_object() to instantiate model objects.
        Map class handles conversion from rows to model instances.
    
    Example:
        >>> rows = load_objects_from_db(conn)
        >>> for row in rows:
        ...     obj = create_object(row['type'], id=row['id'], pos=(row['x'], row['y']))
    """
    cur = conn.execute("SELECT * FROM game_objects")
    return cur.fetchall()


def log_event(conn: sqlite3.Connection, timestamp: float, event_type: str, message: str, 
              obj=None, pos: Optional[Position] = None):
    """Log a game event to the database.
    
    Args:
        conn: Database connection
        timestamp: Game time in seconds
        event_type: Type of event (e.g., 'robot_move', 'storage_full', 'mine_empty')
        message: Human-readable event description
        obj: Optional game object related to the event
        pos: Optional position tuple (x, y)
    """
    obj_id = getattr(obj, 'id', None) if obj else None
    obj_type = type(obj).__name__.lower() if obj else None
    x, y = pos if pos else (None, None)
    
    conn.execute(
        """
        INSERT INTO game_events (timestamp, object_id, object_type, event_type, message, x, y)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp, obj_id, obj_type, event_type, message, x, y)
    )
    conn.commit()


def get_recent_events(conn: sqlite3.Connection, limit: int = 20):
    """Get recent game events, oldest first (newest at bottom).
    
    Args:
        conn: Database connection
        limit: Maximum number of events to return
        
    Returns:
        List of event rows (oldest first, newest last)
    """
    cursor = conn.execute(
        """
        SELECT timestamp, object_id, object_type, event_type, message, x, y
        FROM game_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    )
    # Reverse the list so oldest is first, newest is last (at bottom of display)
    return list(reversed(cursor.fetchall()))
