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

from database import (
    init_game_db, 
    delete_object_db, 
    load_objects_from_db, 
    log_event,
    get_map_settings,
    save_map_settings,
    clear_all_objects,
    clear_map_settings,
    persist_object
)
from models import Robot, Mine, Storage, Base, Rock
from exceptions import MapError, ValidationError

Position = Tuple[int, int]


class Map:
    """Game world map managing all objects and their spatial relationships."""
 
    
    def __init__(self, width: int = 100, height: int = 100, conn: Optional[sqlite3.Connection] = None):
        self.width = width
        self.height = height
        self.conn = conn
        self.cells: Dict[Position, object] = {}
        # Initialize database schema if connection provided.
        if self.conn:
            init_game_db(self.conn)
            # Load map settings from DB; fall back to defaults
            self._load_map_settings()
            # Load existing objects from DB into memory
            self._load_objects_from_db()

    def _load_map_settings(self) -> None:
        """Load map dimensions from game_settings, if present.

        Falls back to current in-memory defaults when settings are missing.
        """
        try:
            settings = get_map_settings(self.conn)
            loaded_from_db = False
            
            if settings['width'] is not None:
                self.width = settings['width']
                loaded_from_db = True
                
            if settings['height'] is not None:
                self.height = settings['height']
                loaded_from_db = True
            
            # Log map load event
            try:
                if loaded_from_db:
                    log_event(self.conn, 'map_loaded', f"Map loaded: width={self.width}, height={self.height}")
                else:
                    log_event(self.conn, 'map_loaded', f"Map loaded with defaults: width={self.width}, height={self.height}")
            except Exception:
                pass
        except Exception:
            # If anything goes wrong, keep defaults
            pass

    def _load_objects_from_db(self) -> None:
        """Load objects from database into memory (self.cells).
        
        Recreates object instances from database rows and populates the cells dict.
        """
        if not self.conn:
            return
        
        try:
            rows = load_objects_from_db(self.conn)
            loaded_count = 0
            
            for row in rows:
                try:
                    obj_type = row['type'] if 'type' in row.keys() else row[1]
                    x = row['x'] if 'x' in row.keys() else row[3]
                    y = row['y'] if 'y' in row.keys() else row[4]
                    name = row['name'] if 'name' in row.keys() else row[2]
                    
                    pos = (int(x), int(y))
                    
                    # Create appropriate object instance
                    if obj_type == 'rock':
                        obj = Rock(name=name or 'Rock', pos=pos)
                    elif obj_type == 'robot':
                        obj = Robot(name=name or 'Robot', pos=pos)
                    elif obj_type == 'mine':
                        obj = Mine(name=name or 'Mine', pos=pos)
                    elif obj_type == 'storage':
                        obj = Storage(name=name or 'Storage', pos=pos)
                    elif obj_type == 'base':
                        obj = Base(name=name or 'Base', pos=pos)
                    else:
                        continue  # Skip unknown types
                    
                    self.cells[pos] = obj
                    loaded_count += 1
                    
                except Exception:
                    continue  # Skip malformed rows
            
            if loaded_count > 0:
                try:
                    log_event(self.conn, 'objects_loaded', f"Loaded {loaded_count} objects from database")
                except Exception:
                    pass
                    
        except Exception:
            # If loading fails, continue with empty map
            pass

    def save_to_db(self) -> None:
        """Persist map settings (width/height) and any in-memory objects to DB.

        Note: Object persistence is best-effort using database.persist_object
        for items present in `cells`. Empty maps will only save dimensions.
        """
        if not self.conn:
            return
        try:
            # Begin a single transaction for atomic persistence
            self.conn.execute("BEGIN")

            # Save map dimensions using database API without auto-commit
            save_map_settings(self.conn, self.width, self.height, commit=False)

            # Remove any stale rows so DB mirrors in-memory state
            self.conn.execute("DELETE FROM game_objects")

            # Persist any objects present in memory without per-object commits
            for pos, obj in list(self.cells.items()):
                try:
                    persist_object(self.conn, obj, commit=False)
                except Exception:
                    # Continue on individual object persist errors
                    continue

            # Commit the full transaction once
            self.conn.commit()

            # Log map save event
            try:
                obj_count = len(self.cells)
                log_event(self.conn, 'map_saved', f"Map saved: width={self.width}, height={self.height}, objects={obj_count}")
            except Exception:
                pass
        except Exception:
            # Avoid crashing on exit due to persistence issues
            try:
                self.conn.rollback()
            except Exception:
                pass

    def reset(self) -> None:
        """Reset map to empty state - clear all objects from memory and database.
        
        Clears:
            - All in-memory cells (objects dict)
            - All objects from the objects table in database
            - Map width/height settings in database
            - Preserves map dimensions (width/height) in memory
        """
        # Clear in-memory objects
        self.cells.clear()
        
        # Clear database using database API
        if self.conn:
            try:
                clear_all_objects(self.conn)
                clear_map_settings(self.conn)
                log_event(self.conn, 'map_reset', f"Map reset to empty state. Dimensions: {self.width}x{self.height}")
            except Exception as e:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                try:
                    log_event(self.conn, 'map_reset_error', f"Error resetting map: {str(e)}")
                except Exception:
                    pass

    def add_object(self, obj, pos: Position):
        """Add object to map at specified position.
        
        Args:
            obj: Game object to add
            pos: (x, y) position to place object
            
        Raises:
            ValueError: If position out of bounds or already occupied
            
        Note:
            Automatically persists to database if connection available.
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

    def object_count(self) -> int:
        """Return number of objects currently stored in memory."""
        return len(self.cells)

    def is_empty(self) -> bool:
        """Return True if no objects are stored in memory."""
        return not self.cells

    def get_viewport_objects(self, width: int, height: int) -> Dict[Position, str]:
        """Return a dict of positions -> type strings within the given viewport.

        Args:
            width: viewport width (columns) starting from x=0
            height: viewport height (rows) starting from y=0

        Returns:
            Dict mapping (x, y) -> lowercase type name
        """
        view: Dict[Position, str] = {}
        max_x = min(self.width, width)
        max_y = min(self.height, height)
        for (x, y), obj in self.cells.items():
            if 0 <= x < max_x and 0 <= y < max_y:
                view[(x, y)] = type(obj).__name__.lower()
        return view
    
    def in_bounds(self, pos: Position) -> bool:
        """Check if position is within map boundaries.
        
        Args:
            pos: (x, y) coordinates to check
            
        Returns:
            True if position is inside map bounds
        """
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_occupied(self, pos: Position) -> bool:
        """Check if position has an object.
        
        Args:
            pos: (x, y) coordinates to check
            
        Returns:
            True if object exists at position
        """
        return pos in self.cells
       
    def generate_border_rocks(self):
        """Generate rock boundary around all map edges.
        generate_border_rocks
        Returns:
            Number of rocks added
            
        Note:
            Creates Rock objects on all four edges (top/bottom/left/right).
            Skips positions already occupied by other objects.
        """
        rocks_added = 0
        # Top and bottom edges
        for x in range(self.width):
            if (x, 0) not in self.cells:
                rock = Rock(name=f"Border Rock", pos=(x, 0))
                self.add_object(rock, (x, 0))
                rocks_added += 1
            if (x, self.height - 1) not in self.cells:
                rock = Rock(name=f"Border Rock", pos=(x, self.height - 1))
                self.add_object(rock, (x, self.height - 1))
                rocks_added += 1
        # Left and right edges
        for y in range(1, self.height - 1):
            if (0, y) not in self.cells:
                rock = Rock(name=f"Border Rock", pos=(0, y))
                self.add_object(rock, (0, y))
                rocks_added += 1
            if (self.width - 1, y) not in self.cells:
                rock = Rock(name=f"Border Rock", pos=(self.width - 1, y))
                self.add_object(rock, (self.width - 1, y))
                rocks_added += 1
        return rocks_added

    def generate_random_rocks(self, count: int = 50, density: float = 0.05):
        """Generate random rocks scattered across the map.
        
        Args:
            count: Target number of rocks to place (if density not used)
            density: Fraction of map cells to fill with rocks (0.0 to 1.0)
                    If > 0, overrides count parameter
        
        Returns:
            Number of rocks successfully added
            
        Note:
            Skips positions already occupied. Uses density if specified,
            otherwise places 'count' rocks at random valid positions.
        """
        # Calculate target count from density if specified
        if density > 0:
            total_cells = self.width * self.height
            count = int(total_cells * density)
        
        rocks_added = 0
        attempts = 0
        max_attempts = count * 10  # Avoid infinite loop
        
        while rocks_added < count and attempts < max_attempts:
            attempts += 1
            # Random position within map bounds
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            
            # Skip if occupied
            if (x, y) in self.cells:
                continue
            
            # Add rock
            rock = Rock(name=f"Rock", pos=(x, y))
            try:
                self.add_object(rock, (x, y))
                rocks_added += 1
            except Exception:
                # Skip on error (shouldn't happen but be safe)
                continue
        
        return rocks_added