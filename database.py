from typing import Optional, Tuple
import sqlite3
from pathlib import Path
from exceptions import DatabaseError

Position = Tuple[int, int]

GAME_DB = Path(__file__).parent / "databases" / "game.db"


def get_connection(path: Optional[Path] = None):
    """Luo SQLite-yhteys WAL-tilassa.
    
    Args:
        path: Tietokantatiedoston polku (oletus: databases/game.db)
        
    Returns:
        sqlite3.Connection row_factory=Row ja WAL-tilassa
        
    Huom:
        Luo databases/-hakemiston jos ei ole olemassa.
        Timeout 10 sekuntia rinnakkaiskäyttöä varten.
    """
    p = path or GAME_DB
    # Varmista että databases-hakemisto on olemassa
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10.0)
    conn.row_factory = sqlite3.Row
    # Käytä WAL-tilaa paremman rinnakkaisuuden vuoksi
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_game_db(conn: sqlite3.Connection):
    """Alusta tietokannan rakenne (idempotentin - turvallinen kutsua useasti).
    
    Luo taulut:
        - game_objects: Fyysiset objektit UNIQUE(x,y) rajoitteella
        - game_settings: Avain-arvo -varasto pelitilalle
        - game_events: Tapahtumaloki
        
    Args:
        conn: Tietokantayhteys
        
    Huom:
        Käyttää CREATE TABLE IF NOT EXISTS - turvallinen olemassa oleville tietokannoille.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS game_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            name TEXT,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            material_stored INTEGER,
            material_capacity INTEGER,
            inventory INTEGER,
            robobasic_code TEXT,
            UNIQUE(x,y)
        )
        """
    )
    # Metataulukko pienille avain-arvo -pareille (kello, asetukset)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS game_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    # Tapahtumataulukko pelin tapahtumille aikaleimoineen
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS game_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT DEFAULT (datetime('now'))
        )
        """
    )
    # Varmista että vanhoissa tietokannoissa on timestamp-sarake
    columns = {row[1] for row in conn.execute("PRAGMA table_info('game_events')")}
    if "timestamp" not in columns:
        # Lisää sarake ilman oletusarvoa (ALTER TABLE SQLitessä sallii vain literaaliset oletukset)
        conn.execute("ALTER TABLE game_events ADD COLUMN timestamp TEXT")
        # Täytä olemassa olevat rivit nykyisellä aikaleimoilla
        conn.execute(
            "UPDATE game_events SET timestamp = COALESCE(timestamp, datetime('now'))"
        )
    # Indeksi nopeampiin aikaleima-hakuihin
    # conn.execute(
    #     """
    #     CREATE INDEX IF NOT EXISTS idx_events_timestamp
    #     ON game_events(timestamp DESC)
    #     """
    # )
    conn.commit()


def persist_object(conn: sqlite3.Connection, obj, commit: bool = True):
    """Save or update game object in database (UPSERT operation).

    Uses ON CONFLICT(x,y) DO UPDATE to handle position uniqueness constraint.
    Falls back to DELETE+INSERT for old databases without UNIQUE constraint.

    Args:
        conn: Database connection
        obj: Game object (Robot, Mine, Storage, Base, Rock)

    Note:
        Auto-commits the transaction unless commit=False (for bulk saves).
        Position (x,y) is the natural key - only one object per cell.

    Example:
        >>> robot = Robot(id=1, name='Bot1', pos=(5,7), inventory=3)
        >>> persist_object(conn, robot)
    """
    obj_type = type(obj).__name__.lower()
    obj_id = getattr(obj, "id", None)
    vals = {
        "type": obj_type,
        "name": getattr(obj, "name", None),
        "x": getattr(obj, "pos")[0] if hasattr(obj, "pos") else None,
        "y": getattr(obj, "pos")[1] if hasattr(obj, "pos") else None,
        "material_stored": getattr(obj, "material_stored", None),
        "material_capacity": getattr(obj, "material_capacity", None),
        "robobasic_code": None,
    }

    # Serialisoi robotin ohjelmakoodi tallennusta varten
    if obj_type == "robot":
        code_lines = getattr(obj, "robobasic_code", None)
        if isinstance(code_lines, list):
            vals["robobasic_code"] = "\n".join(code_lines)
        elif isinstance(code_lines, str):
            vals["robobasic_code"] = code_lines

    # Käytä UPSERT koordinaattien mukaan jotta koordinaatit ovat auktoritatiiviset.
    # Jos objektilla on ID, käytä sitä; muuten anna tietokannan generoida
    try:
        if obj_id is not None:
            # Lisää eksplisiittisellä ID:llä
            cur = conn.execute(
                """
                INSERT INTO game_objects (id, type, name, x, y, material_stored, material_capacity, robobasic_code)
                VALUES (:id, :type, :name, :x, :y, :material_stored, :material_capacity, :robobasic_code)
                ON CONFLICT(x,y) DO UPDATE SET
                    id=excluded.id,
                    type=excluded.type,
                    name=excluded.name,
                    material_stored=excluded.material_stored,
                    material_capacity=excluded.material_capacity,
                    robobasic_code=excluded.robobasic_code
                """,
                {**vals, "id": obj_id},
            )
        else:
            # Anna tietokannan generoida ID automaattisesti
            cur = conn.execute(
                """
                INSERT INTO game_objects (type, name, x, y, material_stored, material_capacity, robobasic_code)
                VALUES (:type, :name, :x, :y, :material_stored, :material_capacity, :robobasic_code)
                ON CONFLICT(x,y) DO UPDATE SET
                    type=excluded.type,
                    name=excluded.name,
                    material_stored=excluded.material_stored,
                    material_capacity=excluded.material_capacity,
                    robobasic_code=excluded.robobasic_code
                """,
                vals,
            )
        if commit:
            conn.commit()

        # Hae kanoninen ID tälle sijainnille ja aseta objektiin
        if vals["x"] is not None and vals["y"] is not None:
            cur2 = conn.execute(
                "SELECT id FROM game_objects WHERE x = ? AND y = ?",
                (vals["x"], vals["y"]),
            )
            row = cur2.fetchone()
            if row:
                try:
                    setattr(obj, "id", row["id"])
                except (AttributeError, TypeError):
                    # Objekti ei tue attribuuttien asettamista (jäädytetty dataclass jne.)
                    pass

    except sqlite3.OperationalError as e:
        # Varautuminen vanhoille tietokannoille ilman UNIQUE(x,y): suorita delete+insert
        msg = str(e)
        if (
            "ON CONFLICT" in msg
            or "does not match any PRIMARY KEY or UNIQUE constraint" in msg
        ):
            if vals["x"] is not None and vals["y"] is not None:
                conn.execute(
                    "DELETE FROM game_objects WHERE x = ? AND y = ?",
                    (vals["x"], vals["y"]),
                )
            if obj_id is not None:
                cur = conn.execute(
                    "INSERT INTO game_objects (id, type, name, x, y, material_capacity, material_stored, robobasic_code) VALUES (:id, :type, :name, :x, :y, :material_capacity, :material_stored, :robobasic_code)",
                    {**vals, "id": obj_id},
                )
            else:
                cur = conn.execute(
                    "INSERT INTO game_objects (type, name, x, y, material_capacity, material_stored, robobasic_code) VALUES (:type, :name, :x, :y, :material_capacity, :material_stored, :robobasic_code)",
                    vals,
                )
            if commit:
                conn.commit()
            new_id = cur.lastrowid if obj_id is None else obj_id
            try:
                setattr(obj, "id", new_id)
            except (AttributeError, TypeError):
                # Object doesn't support attribute assignment
                pass
        else:
            # Unexpected OperationalError, wrap and re-raise
            raise DatabaseError(
                f"Database operation failed: {e}",
                details={"error": str(e), "object": vals},
            ) from e


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


def log_event(conn: sqlite3.Connection, event_type: str, message: str):
    """Kirjaa pelitapahtuma tietokantaan.
    
    Args:
        conn: Tietokantayhteys
        event_type: Tapahtuman tyyppi (esim. 'robot_move', 'storage_full', 'mine_empty')
        message: Ihmisluettava tapahtumakuvaus
        obj: Valinnainen peliobjekti liittyen tapahtumaan
        pos: Valinnainen sijaintitupla (x, y)"""

    try:
        conn.execute(
            """
            INSERT INTO game_events (event_type, message, timestamp)
            VALUES (?, ?, datetime('now'))
            """,
            (event_type, message),
        )
    except sqlite3.OperationalError:
        # Varautuminen vanhoille tietokannoille ilman timestamp-saraketta
        conn.execute(
            """
            INSERT INTO game_events (event_type, message)
            VALUES (?, ?)
            """,
            (event_type, message),
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
        SELECT id, timestamp, event_type, message
        FROM game_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    # Käännä lista niin että vanhimmat ovat ensin, uusimmat viimeisenä (näytön alareunassa)
    return list(reversed(cursor.fetchall()))


def get_latest_event_id(conn: sqlite3.Connection) -> Optional[int]:
    """Palauta uusimman tapahtuman ID tai None jos ei tapahtumia."""
    cur = conn.execute("SELECT id FROM game_events ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    return int(row["id"]) if row else None


# ============================================================================
# Kartan asetustoiminnot
# ============================================================================


def get_map_settings(conn: sqlite3.Connection) -> dict:
    """Get map width and height from game_settings.

    Args:
        conn: Database connection

    Returns:
        Dict with 'width' and 'height' keys (None if not found)
    """
    try:
        cur = conn.execute(
            "SELECT key, value FROM game_settings WHERE key IN ('map_width', 'map_height')"
        )
        rows = {row[0]: row[1] for row in cur.fetchall()}

        width = None
        height = None

        if "map_width" in rows:
            try:
                width = int(rows["map_width"])
            except (TypeError, ValueError):
                pass

        if "map_height" in rows:
            try:
                height = int(rows["map_height"])
            except (TypeError, ValueError):
                pass

        return {"width": width, "height": height}
    except Exception:
        return {"width": None, "height": None}


def save_map_settings(
    conn: sqlite3.Connection, width: int, height: int, commit: bool = True
) -> None:
    """Save map dimensions to game_settings.

    Args:
        conn: Database connection
        width: Map width
        height: Map height
        commit: Whether to commit immediately (set False for batch transactions)
    """
    conn.execute(
        "INSERT INTO game_settings(key, value) VALUES('map_width', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(width),),
    )
    conn.execute(
        "INSERT INTO game_settings(key, value) VALUES('map_height', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(height),),
    )
    if commit:
        conn.commit()


def get_all_settings(conn: sqlite3.Connection):
    """Palauta kaikki asetusrivit (avain, arvo) -pareina."""
    try:
        cur = conn.execute("SELECT key, value FROM game_settings ORDER BY key")
        return cur.fetchall()
    except Exception:
        return []


def get_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    """Get a single setting value.

    Args:
        conn: Database connection
        key: Setting key

    Returns:
        Setting value or None if not found
    """
    try:
        cur = conn.execute("SELECT value FROM game_settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        return None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Set a single setting value.

    Args:
        conn: Database connection
        key: Setting key
        value: Setting value
    """
    conn.execute(
        "INSERT INTO game_settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def clear_all_objects(conn: sqlite3.Connection, commit: bool = True) -> None:
    """Delete all objects from game_objects table.

    Args:
        conn: Database connection
        commit: Whether to commit immediately (set False for batch transactions)
    """
    conn.execute("DELETE FROM game_objects")
    if commit:
        conn.commit()


def clear_all_settings(conn: sqlite3.Connection) -> None:
    """Delete all settings from game_settings table.

    Args:
        conn: Database connection
    """
    conn.execute("DELETE FROM game_settings")
    conn.commit()


def clear_map_settings(conn: sqlite3.Connection) -> None:
    """Poista vain kartalle spesifit asetukset (leveys/korkeus)."""
    conn.execute("DELETE FROM game_settings WHERE key IN ('map_width', 'map_height')")
    conn.commit()


def get_object_count(conn: sqlite3.Connection) -> int:
    """Get total number of objects in database.

    Args:
        conn: Database connection

    Returns:
        Count of objects
    """
    try:
        cur = conn.execute("SELECT COUNT(*) FROM game_objects")
        return cur.fetchone()[0]
    except Exception:
        return 0
