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

from .db import init_game_db, persist_object, delete_object_db, load_objects_from_db, log_event
from .models import Robot, Mine, Storage, Base, Rock
from .exceptions import MapError, ValidationError

Position = Tuple[int, int]


class Map:
    """Game world map managing all objects and their spatial relationships.
    
    Provides grid-based world with:
        - Position-based object storage (one object per cell)
        - Robot movement with pathfinding
        - Material production/consumption systems
        - Transfer operations (1 material/second)
        - RoboBASIC program execution
        
    Attributes:
        width: Map width in cells
        height: Map height in cells
        conn: Optional SQLite connection for persistence
        cells: Dict mapping (x,y) positions to game objects
        
    Example:
        >>> conn = get_game_conn()
        >>> game_map = Map(width=30, height=30, conn=conn)
        >>> robot = Robot(id=1, pos=(5, 7))
        >>> game_map.add_object(robot, (5, 7))
    """
    
    def __init__(self, width: int = 100, height: int = 100, conn: Optional[sqlite3.Connection] = None):
        """Initialize game map and optionally load objects from database.
        
        Args:
            width: Map width in cells (default 100)
            height: Map height in cells (default 100)
            conn: Optional database connection for persistence
            
        Note:
            If conn provided, initializes schema and loads existing objects.
        """
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

        # Simpler movement system: robots store their own state
        # No background thread; movement happens on explicit tick_movement() calls

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

    def get(self, pos: Position):
        """Get object at position.
        
        Args:
            pos: (x, y) coordinates
            
        Returns:
            Object at position or None if empty
        """
        return self.cells.get(pos)
    
    def get_adjacent_objects(self, pos: Position):
        """Get objects in 4-directional adjacent cells (up/down/left/right).
        
        Args:
            pos: Center position
            
        Returns:
            List of objects in adjacent cells (0-4 objects)
            
        Note:
            Does not include diagonals. Returns empty list if no adjacent objects.
        """
        x, y = pos
        adjacent = []
        for dx, dy in [(0, 1), (0, -1), (-1, 0), (1, 0)]:
            adj_pos = (x + dx, y + dy)
            obj = self.get(adj_pos)
            if obj:
                adjacent.append(obj)
        return adjacent

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

    def remove_object(self, pos_or_id):
        """Remove object by position or ID.
        
        Args:
            pos_or_id: Either (x,y) position tuple or integer object ID
            
        Returns:
            Removed object or None if not found
            
        Note:
            Searches in-memory cells first, then database if connection available.
            Automatically removes from database.
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
        except (ValueError, TypeError):
            # Invalid ID format
            raise ValidationError(
                f"Invalid object ID: {pos_or_id}", 
                details={"input": pos_or_id}
            )

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

        # If not in memory, try to remove from DB
        if self.conn:
            cur = self.conn.execute("SELECT x,y FROM game_objects WHERE id = ?", (oid,))
            row = cur.fetchone()
            if row:
                pos = (row['x'], row['y'])
                obj = self.cells.pop(pos, None)
                delete_object_db(self.conn, pos)
                return obj

        # Object not found
        raise MapError(
            f"Object with ID {oid} not found",
            details={"id": oid}
        )

    def move_object(self, from_pos: Position, to_pos: Position):
        """Move object from one position to another instantly.
        
        Args:
            from_pos: Current object position
            to_pos: Destination position
            
        Returns:
            True if successful
            
        Raises:
            ValueError: If positions out of bounds, source empty, or destination occupied
            
        Note:
            This is instant teleport, not pathfinding movement.
            For robot movement, use command_move_robot() instead.
            Automatically updates database with delete+persist.
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
            # Remove the old DB row for the source position before persisting
            # the object at its new coordinates. Without this, moving an
            # object can insert a new row at the new coordinates and leave
            # the old row behind, causing duplicate entries for the same
            # logical object in the DB.
            try:
                delete_object_db(self.conn, from_pos)
            except Exception:
                # best-effort: if deletion fails, continue and try to persist
                pass
            persist_object(self.conn, obj)
        return True

    # ==================== Movement System ====================
    # Robots can be assigned movement targets. Each robot stores its own path.
    # Call tick_movement() once per game second to advance all robots one step.
    
    def command_move_robot(self, robot_id: int, target: Position, stop_distance: int = 0) -> bool:
        """Assign robot to move to target position using pathfinding.
        
        Args:
            robot_id: ID of the robot to move
            target: Target position (x, y)
            stop_distance: Stop N cells away from target (0 = go all the way)
        
        Returns:
            True if movement started, False if already at target or no path found
            
        Raises:
            ValueError: If robot not found, target invalid, or target occupied (when stop_distance=0)
            
        Note:
            Uses BFS pathfinding. Stores path in robot._move_path for tick_movement().
            Automatically truncates path if stop_distance > 0.
        """
        # Find robot by ID
        robot = None
        robot_pos = None
        for pos, obj in self.cells.items():
            if isinstance(obj, Robot) and getattr(obj, 'id', None) == robot_id:
                robot = obj
                robot_pos = pos
                break
        
        if robot is None:
            raise ValueError(f'Robot id {robot_id} not found')
        
        if not self.in_bounds(target):
            raise ValueError(f'Target {target} out of bounds')
        
        # Calculate Manhattan distance to target
        current_distance = abs(robot_pos[0] - target[0]) + abs(robot_pos[1] - target[1])
        
        # If already at desired distance, return False
        if current_distance == stop_distance:
            return False
        
        if robot_pos == target:
            return False  # Already at target
        
        if target in self.cells and stop_distance == 0:
            raise ValueError(f'Target {target} is occupied')
        
        # Compute path using BFS
        path = self._find_path(robot_pos, target)
        if not path:
            return False  # No path available
        
        # If stop_distance > 0, truncate path to stop N cells away
        if stop_distance > 0 and len(path) > stop_distance:
            path = path[:-stop_distance]
        
        # If path is empty after truncation, already at target distance
        if not path:
            return False
        
        # Store movement state on the robot object itself
        robot._move_target = target
        robot._move_path = path
        robot._move_stop_distance = stop_distance
        return True
    
    def tick_movement(self):
        """Advance all robots one step along their paths.
        
        Called once per game second (or as needed). Each robot with active movement
        takes one step toward its goal. If path is blocked, automatically recomputes.
        
        Note:
            - Moves robots one cell per tick
            - Automatically clears path when destination reached
            - Logs movement events to database if connection available
            - Stops if path blocked and can't be recomputed
        """
        from .clock import GameClock
        # Get game time for event logging
        game_seconds = 0
        if self.conn:
            try:
                cursor = self.conn.execute("SELECT value FROM game_meta WHERE key = 'game_seconds'")
                row = cursor.fetchone()
                if row:
                    game_seconds = float(row[0])
            except Exception:
                pass
        
        # Find all robots with active movement targets
        for pos, obj in list(self.cells.items()):
            if not isinstance(obj, Robot):
                continue
            
            target = getattr(obj, '_move_target', None)
            path = getattr(obj, '_move_path', None)
            
            if target is None or path is None or len(path) == 0:
                # No active movement
                continue
            
            # Check if robot is still where we expect
            if pos not in self.cells or self.cells[pos] is not obj:
                # Robot was removed or moved externally; clear movement
                obj._move_target = None
                obj._move_path = None
                continue
            
            # Try to take the next step
            next_pos = path[0]
            
            if next_pos not in self.cells:
                # Path is still clear; move robot
                try:
                    self.move_object(pos, next_pos)
                    # Remove taken step from path
                    obj._move_path = path[1:]
                    
                    # Check if we've reached the target
                    if next_pos == target:
                        obj._move_target = None
                        obj._move_path = None
                        # Log arrival event
                        if self.conn:
                            name = getattr(obj, 'name', f'Robot {obj.id}')
                            log_event(self.conn, game_seconds, 'robot_arrived', 
                                     f'{name} arrived at ({next_pos[0]},{next_pos[1]})', obj, next_pos)
                except Exception:
                    # Move failed; clear the movement
                    obj._move_target = None
                    obj._move_path = None
            else:
                # Next step is blocked; try to recompute path
                new_path = self._find_path(next_pos, target)
                if new_path:
                    obj._move_path = new_path
                else:
                    # No path available; give up
                    obj._move_target = None
                    obj._move_path = None
                    # Log blocked event
                    if self.conn:
                        name = getattr(obj, 'name', f'Robot {obj.id}')
                        log_event(self.conn, game_seconds, 'robot_blocked', 
                                 f'{name} blocked at ({pos[0]},{pos[1]}), cannot reach target', obj, pos)
    
    def tick_transfer(self, game_seconds: int):
        """Handle gradual material transfer for robots (1 material/second).
        
        Args:
            game_seconds: Current game time in seconds
            
        Note:
            - Transfers 1 material per second from source to robot (loading)
            - Transfers 1 material per second from robot to destination (unloading)
            - Automatically stops when source empty, destination full, or robot capacity reached
            - Logs transfer completion events to database
            - Works with Mine, Storage, Base, and other Robot objects
        """
        from .models import Robot, Mine, Base, Storage
        from .db import persist_object, log_event
        
        for pos, obj in list(self.cells.items()):
            if not isinstance(obj, Robot):
                continue
                
            # Initialize fields if missing
            if not hasattr(obj, '_loading_from'):
                obj._loading_from = None
            if not hasattr(obj, '_loading_amount'):
                obj._loading_amount = None
            if not hasattr(obj, '_unloading_to'):
                obj._unloading_to = None
            if not hasattr(obj, '_unloading_amount'):
                obj._unloading_amount = None
            if not hasattr(obj, '_last_transfer_time'):
                obj._last_transfer_time = 0.0
            
            # Handle loading
            if obj._loading_from is not None and obj._loading_amount is not None:
                source = obj._loading_from
                
                # Check early termination conditions
                source_empty = False
                if hasattr(source, 'stored'):
                    source_empty = source.stored == 0
                elif isinstance(source, Robot):
                    source_empty = source.inventory == 0
                    
                robot_full = obj.inventory >= obj.capacity
                
                # If robot is full or source is empty, stop loading immediately
                if robot_full or source_empty:
                    if self.conn:
                        source_name = getattr(source, 'name', type(source).__name__)
                        if robot_full:
                            log_event(self.conn, game_seconds, 'robot_full', 
                                     f'Robot {obj.id} inventory full ({obj.inventory}/{obj.capacity})', obj, pos)
                        log_event(self.conn, game_seconds, 'robot_loaded', 
                                 f'Robot {obj.id} finished loading from {source_name} at ({pos[0]},{pos[1]})', obj, pos)
                    obj._loading_from = None
                    obj._loading_amount = None
                    continue
                
                # Check if enough time passed (1 second)
                if game_seconds >= obj._last_transfer_time + 1:
                    # Transfer 1 material
                    free = obj.capacity - obj.inventory
                    if free > 0:
                        # Withdraw 1 material from source
                        if hasattr(source, 'withdraw'):
                            taken = source.withdraw(1)
                        elif isinstance(source, Robot):
                            taken = min(1, source.inventory)
                            source.inventory -= taken
                        else:
                            taken = 0
                        
                        if taken > 0:
                            obj.inventory += taken
                            obj._loading_amount -= taken
                            obj._last_transfer_time = game_seconds
                            
                            # Persist both objects
                            if self.conn:
                                persist_object(self.conn, obj)
                                persist_object(self.conn, source)
                    
                    # Check if done loading
                    if obj._loading_amount <= 0 or obj.inventory >= obj.capacity or (hasattr(source, 'stored') and source.stored == 0) or (isinstance(source, Robot) and source.inventory == 0):
                        # Log completion
                        if self.conn:
                            source_name = getattr(source, 'name', type(source).__name__)
                            log_event(self.conn, game_seconds, 'robot_loaded', 
                                     f'Robot {obj.id} finished loading from {source_name} at ({pos[0]},{pos[1]})', obj, pos)
                            if obj.inventory >= obj.capacity:
                                log_event(self.conn, game_seconds, 'robot_full', 
                                         f'Robot {obj.id} inventory full ({obj.inventory}/{obj.capacity})', obj, pos)
                        obj._loading_from = None
                        obj._loading_amount = None
            
            # Handle unloading
            elif obj._unloading_to is not None and obj._unloading_amount is not None:
                target = obj._unloading_to
                
                # Check early termination conditions
                robot_empty = obj.inventory == 0
                
                target_full = False
                if hasattr(target, 'stored') and hasattr(target, 'capacity'):
                    target_full = target.stored >= target.capacity
                elif isinstance(target, Robot):
                    target_full = target.inventory >= target.capacity
                    
                # If robot is empty or target is full, stop unloading immediately
                if robot_empty or target_full:
                    if self.conn:
                        target_name = getattr(target, 'name', type(target).__name__)
                        if target_full:
                            log_event(self.conn, game_seconds, 'target_full', 
                                     f'{target_name} is full ({target.stored if hasattr(target, "stored") else target.inventory}/{target.capacity})', target, target.pos if hasattr(target, "pos") else None)
                        log_event(self.conn, game_seconds, 'robot_unloaded', 
                                 f'Robot {obj.id} finished unloading to {target_name} at ({pos[0]},{pos[1]})', obj, pos)
                    obj._unloading_to = None
                    obj._unloading_amount = None
                    continue
                
                # Check if enough time passed (1 second)
                if game_seconds >= obj._last_transfer_time + 1:
                    # Transfer 1 material
                    if obj.inventory > 0:
                        # Deposit 1 material to target
                        if hasattr(target, 'store'):
                            stored = target.store(1)
                        elif hasattr(target, 'deposit'):
                            stored = target.deposit(1)
                        elif isinstance(target, Robot):
                            free = target.capacity - target.inventory
                            stored = min(1, free)
                            target.inventory += stored
                        else:
                            stored = 0
                        
                        if stored > 0:
                            obj.inventory -= stored
                            obj._unloading_amount -= stored
                            obj._last_transfer_time = game_seconds
                            
                            # Persist both objects
                            if self.conn:
                                persist_object(self.conn, obj)
                                persist_object(self.conn, target)
                    
                    # Check if done unloading
                    if obj._unloading_amount <= 0 or obj.inventory == 0 or (hasattr(target, 'stored') and hasattr(target, 'capacity') and target.stored >= target.capacity) or (isinstance(target, Robot) and target.inventory >= target.capacity):
                        # Log completion
                        if self.conn:
                            target_name = getattr(target, 'name', type(target).__name__)
                            log_event(self.conn, game_seconds, 'robot_unloaded', 
                                     f'Robot {obj.id} finished unloading to {target_name} at ({pos[0]},{pos[1]})', obj, pos)
                            if obj.inventory == 0:
                                log_event(self.conn, game_seconds, 'robot_empty', 
                                         f'Robot {obj.id} inventory empty', obj, pos)
                        obj._unloading_to = None
                        obj._unloading_amount = None
    
    def tick_production(self, game_seconds: int):
        """Handle material production in mines and consumption in bases.
        
        Args:
            game_seconds: Current game time in seconds
            
        Note:
            - Mines: Produce 1 material/10s if not full (max capacity)
            - Bases: Consume 1 material/10s if available
            - Storage: Monitors full/empty status
            - Logs: mine_full, mine_empty, base_empty, base_supplied, storage_full, storage_empty events
            - Automatically persists changed objects to database
        """
        from .models import Mine, Base, Storage
        
        for pos, obj in self.cells.items():
            if isinstance(obj, Mine):
                # Check if mine was full before production
                was_full = obj.stored >= obj.capacity
                # Mines produce 1 material every 10 seconds if not full
                produced = obj.produce(game_seconds)
                if produced > 0 and self.conn:
                    from .db import persist_object
                    persist_object(self.conn, obj)
                # Check if mine became full
                if obj.stored >= obj.capacity and not was_full and self.conn:
                    name = getattr(obj, 'name', f'Mine {obj.id}')
                    log_event(self.conn, game_seconds, 'mine_full', 
                             f'{name} at ({pos[0]},{pos[1]}) is full ({obj.stored}/{obj.capacity})', obj, pos)
                # Check if mine is now empty (all materials withdrawn)
                if obj.stored == 0 and self.conn:
                    name = getattr(obj, 'name', f'Mine {obj.id}')
                    log_event(self.conn, game_seconds, 'mine_empty', 
                             f'{name} at ({pos[0]},{pos[1]}) is empty', obj, pos)
            elif isinstance(obj, Base):
                # Check if base was empty before consumption
                was_empty = obj.stored == 0
                # Bases consume 1 material every 10 seconds if material available
                consumed = obj.consume(game_seconds)
                if consumed > 0 and self.conn:
                    from .db import persist_object
                    persist_object(self.conn, obj)
                # Check if base became empty
                if obj.stored == 0 and not was_empty and self.conn:
                    name = getattr(obj, 'name', f'Base {obj.id}')
                    log_event(self.conn, game_seconds, 'base_empty', 
                             f'{name} at ({pos[0]},{pos[1]}) is empty', obj, pos)
                # Check if base became full
                if obj.stored > 0 and was_empty and self.conn:
                    name = getattr(obj, 'name', f'Base {obj.id}')
                    log_event(self.conn, game_seconds, 'base_supplied', 
                             f'{name} at ({pos[0]},{pos[1]}) has materials ({obj.stored})', obj, pos)
            elif isinstance(obj, Storage):
                # Check storage status for full/empty conditions
                if obj.stored >= obj.capacity and self.conn:
                    name = getattr(obj, 'name', f'Storage {obj.id}')
                    # Log only once when it becomes full (avoid spam)
                    if not hasattr(obj, '_logged_full') or not obj._logged_full:
                        log_event(self.conn, game_seconds, 'storage_full', 
                                 f'{name} at ({pos[0]},{pos[1]}) is full ({obj.stored}/{obj.capacity})', obj, pos)
                        obj._logged_full = True
                else:
                    if hasattr(obj, '_logged_full'):
                        obj._logged_full = False
                if obj.stored == 0 and self.conn:
                    name = getattr(obj, 'name', f'Storage {obj.id}')
                    # Log only once when it becomes empty (avoid spam)
                    if not hasattr(obj, '_logged_empty') or not obj._logged_empty:
                        log_event(self.conn, game_seconds, 'storage_empty', 
                                 f'{name} at ({pos[0]},{pos[1]}) is empty', obj, pos)
                        obj._logged_empty = True
                else:
                    if hasattr(obj, '_logged_empty'):
                        obj._logged_empty = False
                    from .db import persist_object
                    persist_object(self.conn, obj)
    
    def tick_programs(self, game_seconds: int):
        """Execute one line of RoboBASIC program for each running robot.
        
        Args:
            game_seconds: Current game time in seconds
            
        Note:
            - Executes 1 line per second for each robot with active program
            - Automatically advances program counter after each line
            - Stops on error or program completion
            - Logs execution events and errors to database
            - Uses RoboBRAIN virtual machine for command execution
        """
        from .models import Robot
        from .robobrain import RoboBRAINExecutor
        
        executor = RoboBRAINExecutor()
        
        for pos, obj in list(self.cells.items()):
            if isinstance(obj, Robot) and obj._program_running:
                # Check if robot is blocked
                if game_seconds < obj._blocked_until:
                    continue
                
                # Execute next line
                result = executor.execute_next_line(obj, self, game_seconds)
                
                # Log errors or status
                if result and self.conn:
                    name = getattr(obj, 'name', f'Robot {obj.id}')
                    log_event(self.conn, game_seconds, 'robot_program', 
                             f'{name}: {result}', obj, pos)
                
                # Persist updated state
                if self.conn:
                    from .db import persist_object
                    persist_object(self.conn, obj)
    
    # ==================== Pathfinding ====================

    def _find_path(self, start: Position, goal: Position) -> List[Position]:
        """Find shortest path from start to goal using BFS pathfinding.
        
        Args:
            start: Starting position (x, y)
            goal: Goal position (x, y)
            
        Returns:
            List of positions to follow (excluding start, including goal).
            Empty list if no path exists or start == goal.
            
        Note:
            - Uses BFS for shortest path (Manhattan distance)
            - Only moves through empty cells (or goal cell)
            - 4-directional movement (up/down/left/right)
            - Ignores diagonal movement
        """
        from collections import deque
        
        if start == goal:
            return []
        
        queue = deque([start])
        visited = {start}
        parent = {start: None}
        
        while queue:
            current = queue.popleft()
            
            # Check all four cardinal neighbors
            for neighbor in self._neighbors(current):
                if not self.in_bounds(neighbor):
                    continue
                if neighbor in visited:
                    continue
                
                # Allow moving through free cells or the goal
                if neighbor in self.cells and neighbor != goal:
                    continue
                
                visited.add(neighbor)
                parent[neighbor] = current
                
                if neighbor == goal:
                    # Reconstruct path
                    path = []
                    node = goal
                    while node is not None:
                        path.append(node)
                        node = parent[node]
                    path.reverse()
                    return path[1:]  # Exclude start
                
                queue.append(neighbor)
        
        return []  # No path found
    
    def _neighbors(self, pos: Position) -> List[Position]:
        """Return valid neighboring positions in 4 directions.
        
        Args:
            pos: Center position
            
        Returns:
            List of (x,y) positions for up/down/left/right neighbors within bounds
            
        Note:
            Only returns positions inside map boundaries. Does not check occupancy.
        """
        x, y = pos
        neighbors = []
        for nx, ny in [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]:
            if self.in_bounds((nx, ny)):
                neighbors.append((nx, ny))
        return neighbors

    def generate_border_rocks(self):
        """Generate rock boundary around all map edges.
        
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

    def generate_terrain_rocks(self, density: float = 0.05, cluster_size: int = 3):
        """Generate natural-looking rock formations inside the map.
        
        Args:
            density: Probability of a rock cluster starting (0.0 to 1.0, default 0.05)
            cluster_size: Average size of rock clusters (default 3)
            
        Returns:
            Number of rocks added
            
        Note:
            - Avoids edges (2 cells from border)
            - Uses random walk algorithm for natural clustering
            - Skips occupied positions
            - Density of 0.05 = ~5% of cells become rock clusters
        """
        rocks_added = 0
        # Avoid edges (already have border rocks)
        for y in range(2, self.height - 2):
            for x in range(2, self.width - 2):
                # Skip if already occupied
                if (x, y) in self.cells:
                    continue
                
                # Random chance to start a cluster
                if random.random() < density:
                    # Create a cluster of rocks
                    cluster_positions = self._generate_rock_cluster((x, y), cluster_size)
                    for pos in cluster_positions:
                        px, py = pos
                        # Check bounds and if position is free
                        if (1 <= px < self.width - 1 and 
                            1 <= py < self.height - 1 and 
                            pos not in self.cells):
                            rock = Rock(name="Rock", pos=pos)
                            self.add_object(rock, pos)
                            rocks_added += 1
        return rocks_added

    def _generate_rock_cluster(self, start_pos: tuple, avg_size: int) -> list:
        """Generate positions for a natural-looking rock cluster using random walk.
        
        Args:
            start_pos: Starting position (x, y)
            avg_size: Average number of rocks in cluster
        
        Returns:
            List of (x, y) positions for the cluster
            
        Note:
            - Uses Gaussian distribution for cluster size variation
            - 8-directional random walk (including diagonals)
            - 70% chance to continue from new position, 30% to return to start
            - Creates organic, non-uniform rock formations
        """
        positions = [start_pos]
        current_pos = start_pos
        size = max(1, int(random.gauss(avg_size, avg_size / 2)))
        
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        
        for _ in range(size - 1):
            # Random walk to adjacent position
            dx, dy = random.choice(directions)
            new_pos = (current_pos[0] + dx, current_pos[1] + dy)
            
            # 70% chance to continue from new position, 30% to return to start
            if random.random() < 0.7:
                current_pos = new_pos
            else:
                current_pos = start_pos
            
            if new_pos not in positions:
                positions.append(new_pos)
        
        return positions

    def generate_full_terrain(self, rock_density: float = 0.05, cluster_size: int = 3):
        """Generate complete terrain: border rocks + interior rock formations.
        
        Args:
            rock_density: Probability of rock cluster formation (0.0 to 1.0)
            cluster_size: Average size of rock clusters
        
        Returns:
            Tuple of (border_rocks_added, terrain_rocks_added)
        """
        border = self.generate_border_rocks()
        terrain = self.generate_terrain_rocks(density=rock_density, cluster_size=cluster_size)
        return border, terrain
