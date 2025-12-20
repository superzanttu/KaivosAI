from typing import Tuple, Dict, Optional, List
import sqlite3
import threading
import time
import random

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

        # Simpler movement system: robots store their own state
        # No background thread; movement happens on explicit tick_movement() calls

    def in_bounds(self, pos: Position) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_occupied(self, pos: Position) -> bool:
        return pos in self.cells

    def get(self, pos: Position):
        return self.cells.get(pos)
    
    def get_adjacent_objects(self, pos: Position):
        """Get objects adjacent to position (up, down, left, right)."""
        x, y = pos
        adjacent = []
        for dx, dy in [(0, 1), (0, -1), (-1, 0), (1, 0)]:
            adj_pos = (x + dx, y + dy)
            obj = self.get(adj_pos)
            if obj:
                adjacent.append(obj)
        return adjacent

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
    
    def command_move_robot(self, robot_id: int, target: Position) -> bool:
        """Assign a robot to move to a target position.
        
        Returns True if movement started, False if already at target or no path found.
        Raises ValueError if robot not found or target invalid.
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
        
        if robot_pos == target:
            return False  # Already at target
        
        if target in self.cells:
            raise ValueError(f'Target {target} is occupied')
        
        # Compute path using BFS
        path = self._find_path(robot_pos, target)
        if not path:
            return False  # No path available
        
        # Store movement state on the robot object itself
        robot._move_target = target
        robot._move_path = path
        return True
    
    def tick_movement(self):
        """Advance all robots one step along their paths.
        
        Call this once per game second (or as needed). Each robot takes one step
        toward its goal. If a path is blocked, it's recomputed.
        """
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
    
    def tick_production(self, game_seconds: int):
        """Handle material production in mines and consumption in bases.
        
        Args:
            game_seconds: Current game time in seconds
        """
        from .models import Mine, Base
        
        for pos, obj in self.cells.items():
            if isinstance(obj, Mine):
                # Mines produce 1 material every 10 seconds if not full
                produced = obj.produce(game_seconds)
                if produced > 0 and self.conn:
                    from .db import persist_object
                    persist_object(self.conn, obj)
            elif isinstance(obj, Base):
                # Bases consume 1 material every 10 seconds if material available
                consumed = obj.consume(game_seconds)
                if consumed > 0 and self.conn:
                    from .db import persist_object
                    persist_object(self.conn, obj)
    
    # ==================== Pathfinding ====================

    def _find_path(self, start: Position, goal: Position) -> List[Position]:
        """Find a path from start to goal using BFS.
        
        Returns a list of positions (including goal, excluding start) to follow.
        Returns empty list if no path exists.
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
        """Return valid neighboring positions (4-directional: up, down, left, right)."""
        x, y = pos
        neighbors = []
        for nx, ny in [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]:
            if self.in_bounds((nx, ny)):
                neighbors.append((nx, ny))
        return neighbors

    def generate_border_rocks(self):
        """Generate rock boundary around map edges."""
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
            density: Probability of a rock cluster starting (0.0 to 1.0)
            cluster_size: Average size of rock clusters
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
            List of (x, y) positions
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
