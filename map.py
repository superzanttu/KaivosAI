"""Game world map and spatial object management.

Handles object placement, movement, pathfinding, and game tick logic.
All game state interactions go through the Map class.

Key responsibilities:
    - Spatial storage (position -> object mapping)
    - Object lifecycle (add, remove, move)
    - Robot movement with pathfinding (BFS algorithm)
    - Material production/consumption ticks
    - Robot transfer operations (loading/unloading)
    - RoboBASIC program execution ticks
    
Threading:
    - Main thread only (no background threads)
    - All ticks called explicitly from CLI refresh_display()
    - Uses DB connection from main thread
"""

from typing import Tuple, Dict, Optional, List
import sqlite3
import threading
import time
import random

from database import init_game_db, persist_object, delete_object_db, load_objects_from_db, log_event
from models import Robot, Mine, Storage, Base, Rock
from exceptions import MapError, ValidationError

Position = Tuple[int, int]


class Map:
    """Game world map managing all objects and their spatial relationships."""
 
    
    def __init__(self, width: int = 1000, height: int = 1000, conn: Optional[sqlite3.Connection] = None):
        self.width = width
        self.height = height
        self.conn = conn
        self.cells: Dict[Position, object] = {}
        # Initialize database schema if connection provided.
        # Avoid calling a non-existent loader; map starts empty by default.
        if self.conn:
            init_game_db(self.conn)
            # Try to load map settings from DB; fall back to defaults
            self._load_map_settings()

    def _load_map_settings(self) -> None:
        """Load map dimensions from game_settings, if present.

        Falls back to current in-memory defaults when settings are missing.
        """
        try:
            cur = self.conn.execute("SELECT key, value FROM game_settings WHERE key IN ('map_width','map_height')")
            rows = {row[0]: row[1] for row in cur.fetchall()}
            loaded_from_db = False
            if 'map_width' in rows:
                try:
                    self.width = int(rows['map_width'])
                    loaded_from_db = True
                except (TypeError, ValueError):
                    pass
            if 'map_height' in rows:
                try:
                    self.height = int(rows['map_height'])
                    loaded_from_db = True
                except (TypeError, ValueError):
                    pass
            # Log map load event
            try:
                if loaded_from_db:
                    log_event(self.conn, 'map_loaded', f"Map loaded: width={self.width}, height={self.height}")
                else:
                    log_event(self.conn, 'map_loaded', f"Map loaded with defaults: width={self.width}, height={self.height}")
            except Exception:
                # Ignore logging failures
                pass
        except Exception:
            # If anything goes wrong, keep defaults
            pass

    def save_to_db(self) -> None:
        """Persist map settings (width/height) and any in-memory objects to DB.

        Note: Object persistence is best-effort using database.persist_object
        for items present in `cells`. Empty maps will only save dimensions.
        """
        if not self.conn:
            return
        try:
            # Upsert map dimensions to game_settings
            self.conn.execute(
                "INSERT INTO game_settings(key,value) VALUES('map_width', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(self.width),)
            )
            self.conn.execute(
                "INSERT INTO game_settings(key,value) VALUES('map_height', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(self.height),)
            )
            # Persist any objects present in memory (optional, noop if none)
            for pos, obj in list(self.cells.items()):
                try:
                    persist_object(self.conn, obj)
                except Exception:
                    # Continue on individual object persist errors
                    continue
            self.conn.commit()
            # Log map save event
            try:
                obj_count = len(self.cells)
                log_event(self.conn, 'map_saved', f"Map saved: width={self.width}, height={self.height}, objects={obj_count}")
            except Exception:
                # Ignore logging failures
                pass
        except Exception:
            # Avoid crashing on exit due to persistence issues
            try:
                self.conn.rollback()
            except Exception:
                pass
    
  