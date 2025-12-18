from typing import Tuple, Dict, Optional, List
import sqlite3
import threading
import time

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

            # movement/tasking state
            self._movement_lock = threading.Lock()
            # robot id -> target position
            self._targets: Dict[int, Position] = {}
            # robot id -> path (list of positions to step through)
            self._paths: Dict[int, List[Position]] = {}
            self._movement_thread: Optional[threading.Thread] = None
            self._movement_stop = threading.Event()
            self._clock = None

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

    # ----------------- Movement / pathfinding -----------------
    def set_clock(self, clock):
        """Attach a GameClock instance to the map and start the movement loop."""
        self._clock = clock
        # start movement thread if not running
        if self._movement_thread and self._movement_thread.is_alive():
            return
        self._movement_stop.clear()
        self._movement_thread = threading.Thread(target=self._movement_loop, daemon=True)
        self._movement_thread.start()

    def stop_movement(self):
        self._movement_stop.set()
        if self._movement_thread:
            self._movement_thread.join(timeout=1)

    def command_move_robot(self, robot_id: int, target: Position) -> bool:
        """Assign a robot to move to target. Returns True if a task was started."""
        # find robot by id
        robot = None
        for o in self.cells.values():
            if isinstance(o, Robot) and getattr(o, 'id', None) == robot_id:
                robot = o
                break
        if robot is None:
            raise ValueError('Robot id not found')
        if not self.in_bounds(target):
            raise ValueError('Target out of bounds')
        if target == robot.pos:
            return False
        # prohibit targeting occupied cell
        if target in self.cells:
            raise ValueError('Target cell is occupied')

        # compute initial path
        path = self._find_path(robot.pos, target)
        if not path:
            # no path available now
            return False

        with self._movement_lock:
            self._targets[robot_id] = target
            self._paths[robot_id] = path
        return True

    def _neighbors(self, pos: Position) -> List[Position]:
        x, y = pos
        for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            yield (nx, ny)

    def _find_path(self, start: Position, goal: Position) -> List[Position]:
        """Simple BFS pathfinder avoiding occupied cells (except start). Returns list of positions (excluding start) to follow."""
        from collections import deque
        if start == goal:
            return []
        q = deque()
        q.append(start)
        prev = {start: None}
        obstacles = set(self.cells.keys())
        # allow start to be treated as free
        obstacles.discard(start)
        # do not allow entering goal if occupied
        if goal in obstacles:
            return []

        found = False
        while q:
            cur = q.popleft()
            for n in self._neighbors(cur):
                if not self.in_bounds(n):
                    continue
                if n in prev:
                    continue
                if n in obstacles:
                    continue
                prev[n] = cur
                if n == goal:
                    found = True
                    q.clear()
                    break
                q.append(n)
        if not found:
            return []
        # reconstruct path
        path = []
        cur = goal
        while cur != start:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path

    def _movement_loop(self):
        last_sec = None
        last_time = time.monotonic()
        while not self._movement_stop.is_set():
            # try to use game clock seconds when available; otherwise fall back to monotonic wall time
            sec = None
            try:
                if self._clock is not None:
                    sec = int(self._clock.seconds)
            except Exception:
                sec = None

            now = time.monotonic()
            # if we have a clock-sec value, step when it increases
            if sec is not None:
                if last_sec is None:
                    last_sec = sec
                elif sec > last_sec:
                    last_sec = sec
                    self._step_movement()
                    last_time = now
            else:
                # fallback: step every ~1.0 second of wall time
                if now - last_time >= 1.0:
                    last_time = now
                    self._step_movement()

            # wait briefly to be responsive to stop
            if self._movement_stop.wait(0.1):
                break

    def _step_movement(self):
        """Perform one movement tick: try to move each tasked robot one step."""
        # copy ids to avoid modification during iteration
        with self._movement_lock:
            robot_ids = list(self._targets.keys())

        for rid in robot_ids:
            with self._movement_lock:
                path = self._paths.get(rid)
                target = self._targets.get(rid)
            # ensure robot still exists and find its current pos
            robot_pos = None
            robot_obj = None
            for p,o in self.cells.items():
                if isinstance(o, Robot) and getattr(o, 'id', None) == rid:
                    robot_pos = p
                    robot_obj = o
                    break
            if robot_pos is None:
                # robot removed
                with self._movement_lock:
                    self._targets.pop(rid, None)
                    self._paths.pop(rid, None)
                continue

            if not path:
                # nothing to do or no path
                continue

            next_step = path[0]
            # if next step is free, move
            if next_step not in self.cells:
                try:
                    self.move_object(robot_pos, next_step)
                except Exception:
                    # move failed unexpectedly; try to recompute path
                    new_path = self._find_path(robot_pos, target)
                    with self._movement_lock:
                        self._paths[rid] = new_path
                    continue
                # moved: pop step
                with self._movement_lock:
                    self._paths[rid] = self._paths[rid][1:]
                    if not self._paths[rid]:
                        # reached target
                        self._targets.pop(rid, None)
                        self._paths.pop(rid, None)
                continue

            # blocked: attempt to recompute path around obstacle
            new_path = self._find_path(robot_pos, target)
            with self._movement_lock:
                self._paths[rid] = new_path
            # if no new path, leave for next tick
