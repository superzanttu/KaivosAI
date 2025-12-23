"""Database migration utilities for KaivosAI.

Provides a safe migration that backs up `game.db` and deduplicates
objects by coordinates (x,y), keeping the row with the highest id.
"""
from pathlib import Path
import shutil
import sqlite3
from typing import Tuple


def backup_db(path: Path) -> Path:
    """Create a backup of the database file next to the original.

    Args:
        path: Path to the original database file (e.g., databases/game.db)

    Returns:
        Path to the created backup file (e.g., databases/game.db.bak)

    Note:
        Uses `copy2` to preserve metadata. Ensures parent directory exists.
    """
    # Ensure parent directory exists for backup
    path.parent.mkdir(parents=True, exist_ok=True)
    bak = path.with_suffix(path.suffix + '.bak')
    shutil.copy2(path, bak)
    return bak


def migrate_deduplicate(path: Path) -> Tuple[int, int]:
    """Backup DB and deduplicate rows by (x,y).

    Returns (before_count, after_count).
    """
    if not path.exists():
        return 0, 0
    bak = backup_db(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('PRAGMA foreign_keys = OFF')
    cur.execute('BEGIN')
    try:
        cur.execute('SELECT COUNT(*) FROM game_objects')
        before = cur.fetchone()[0]
        # create new table with UNIQUE(x,y)
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS game_objects_new (
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
            '''
        )
        # insert one row per (x,y) keeping the highest id
        cur.execute(
            '''
            INSERT OR REPLACE INTO game_objects_new (type,name,x,y,capacity,stored,durability,bank,inventory)
            SELECT g.type,g.name,g.x,g.y,g.capacity,g.stored,g.durability,g.bank,g.inventory
            FROM game_objects g
            WHERE g.id IN (SELECT MAX(id) FROM game_objects GROUP BY x,y)
            '''
        )
        cur.execute('DROP TABLE game_objects')
        cur.execute('ALTER TABLE game_objects_new RENAME TO game_objects')
        conn.commit()
        cur.execute('SELECT COUNT(*) FROM game_objects')
        after = cur.fetchone()[0]
        return before, after
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    p = Path('game.db')
    b, a = migrate_deduplicate(p)
    print(f'Rows before: {b}  after: {a}')
