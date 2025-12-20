"""CLI and Urwid TUI for KaivosAI.

Main user interface providing:
    - Terminal-based UI using Urwid library
    - Natural language command processor with aliases
    - Colored map display (robots, mines, storage, bases, rocks)
    - Object list with inventory/material status
    - Recent events display
    - RoboBASIC code editor with syntax validation
    - Game clock display (Week/Day/Time format)
    - Auto-refresh every 0.5s for real-time updates
    
Key components:
    - run_urwid_tui(): Main TUI loop (entry point)
    - process_command(): Natural language command parser (~500 lines)
    - build_map_display(): Colored ASCII map with legend
    - build_object_list(): Object status with materials/inventory
    - build_events_display(): Recent game events log
    - show_command_editor(): Robot code editor with validation
    
Command categories:
    - Object management: create, delete, move
    - Robot control: goto, load, unload, code/start/pause
    - Map operations: show, list, terrain, demo, reset
    - System: help, version, quit, pause, resume
    
Threading:
    - Main thread: Urwid event loop + UI refresh
    - Background thread: GameClock (time progression)
    
Note:
    Display updates 2x per second (0.5s tick rate).
    All game logic ticks (movement, production, transfers, programs) called from refresh_display().
"""
from typing import Tuple, List
import shlex
import random
import time
import os

from .db import get_game_conn, init_game_db, log_event
from .map import Map
from .models import Robot, Mine, Storage, Base, Rock, create_object
from .clock import GameClock
from .exceptions import CommandError, RobotError, MapError, ValidationError
from . import VERSION

Position = Tuple[int, int]

import urwid  # type: ignore

# Command aliases (short -> full form)
COMMAND_ALIASES = {
    # Objects
    'r': 'robot',
    'rob': 'robot',
    'bot': 'robot',
    'm': 'mine',
    's': 'storage',
    'stor': 'storage',
    'b': 'base',
    'o': 'object',
    'obj': 'object',
    # Actions
    'c': 'create',
    'add': 'create',
    'd': 'delete',
    'del': 'delete',
    'rem': 'delete',
    'remove': 'delete',
    'g': 'goto',
    'go': 'goto',
    'move': 'goto',
    'l': 'load',
    'u': 'unload',
    'dump': 'unload',
    # Map commands (map terrain, map demo, map reset, map show, map list)
    'show': 'map',
    'view': 'map',
    'ls': 'list',
    'objects': 'list',
    't': 'terrain',
    'gen': 'terrain',
    'generate': 'terrain',
    # System commands (system help, system version, system quit, system pause, system resume)
    'sys': 'system',
    'h': 'help',
    '?': 'help',
    'q': 'quit',
    'exit': 'quit',
    'p': 'pause',
    'stop': 'pause',
    'start': 'resume',
    'unpause': 'resume',
    'v': 'version',
    'ver': 'version',
    # Other
    'what': 'inspect',
    'look': 'inspect',
    'check': 'inspect',
}

# Robot-specific action aliases (contextual, applied only after 'robot' command)
ROBOT_ACTION_ALIASES = {
    # Movement
    'g': 'goto',
    'go': 'goto',
    'move': 'goto',
    'm': 'goto',
    'walk': 'goto',
    # Load/Unload
    'l': 'load',
    'load': 'load',
    'take': 'load',
    'pickup': 'load',
    'get': 'load',
    'u': 'unload',
    'ul': 'unload',
    'unload': 'unload',
    'dump': 'unload',
    'drop': 'unload',
    'put': 'unload',
    'store': 'unload',
    # Program control
    'c': 'code',
    'code': 'code',
    'program': 'code',
    'prg': 'code',
    'prog': 'code',
    'edit': 'code',
    's': 'start',
    'start': 'start',
    'run': 'start',
    'execute': 'start',
    'p': 'pause',
    'pause': 'pause',
    'halt': 'pause',
    'stop': 'pause',
    'end': 'pause',
}

# Available commands for tab completion
COMPLETIONS = [
    'robot', 'mine', 'storage', 'base', 'rock', 'object',
    'create', 'delete', 'goto', 'load', 'unload',
    'map', 'terrain', 'demo', 'reset', 'list', 'inspect',
    'system', 'help', 'quit', 'pause', 'resume', 'version',
]


class CLIController:
    """Headless-friendly command controller for testing and reuse.

    Provides the same command parsing and handler logic used by the TUI,
    but without Urwid UI dependencies. Accepts injected map/clock/conn and
    optional code editor callback for editing commands when available.
    """

    def __init__(self, game_map: Map, clock: GameClock, conn, show_command_editor=None):
        self.game_map = game_map
        self.clock = clock
        self.conn = conn
        self.show_command_editor = show_command_editor

    def _build_help_text(self) -> str:
        return ("Commands (with shortcuts):\n"
                "\n"
                "ROBOT CONTROL:\n"
                "• robot ID goto X Y [d N] (r ID g X Y [d N]) - move robot to position (stop N cells away)\n"
                "• robot ID goto OBJ_ID [d N] (r ID g OBJ_ID [d N]) - move robot near object (stop N cells away)\n"
                "• robot ID load [amount] (r ID l [N]) - load N materials from adjacent object\n"
                "• robot ID unload [amount] (r ID u [N]) - unload N materials to adjacent object\n"
                "• robot ID code (r ID c) - open robot code editor (F2=save, ESC=cancel)\n"
                "• robot ID start (r ID s) - start executing robot code\n"
                "• robot ID pause (r ID p) - pause robot code execution\n"
                "\n"
                "OBJECT MANAGEMENT:\n"
                "• create TYPE X Y (c TYPE X Y) - create object at position (types: robot, mine, storage, base)\n"
                "• delete ID (d ID) - remove object by ID\n"
                "• delete X Y (d X Y) - remove object at position\n"
                "• inspect X Y - inspect position (show what's there)\n"
                "\n"
                "MAP OPERATIONS:\n"
                "• map terrain [density] [size] (map t [D] [S]) - generate terrain\n"
                "  density: 0.0-1.0 (default 0.05), size: cluster size 1+ (default 3)\n"
                "• map demo - add 4 demo objects at random positions\n"
                "• map reset - clear map and reset clock\n"
                "\n"
                "SYSTEM COMMANDS:\n"
                "• system pause - pause clock (stops production/consumption)\n"
                "• system resume - resume clock\n"
                "• system optimize - renumber object IDs sequentially (1,2,3...)\n"
                "• system version - show KaivosAI version\n"
                "• system help - show this help text\n"
                "• system quit (quit) - exit game\n"
                "\n"
                "TIPS:\n"
                "• Use 'r' instead of 'robot', 'c' instead of 'create', 'd' instead of 'delete'\n"
                "• TAB for command completion\n"
                "• Program syntax: type 'help' while editing to see RoboBASIC commands")

    def _handle_system(self, parts: list) -> str:
        from .models import Robot, Mine, Storage, Base
        from .db import persist_object
        import urwid

        if len(parts) < 2:
            return 'Usage: system <help|version|quit|pause|resume|optimize>'
        sub = parts[1]

        if sub == 'quit':
            raise urwid.ExitMainLoop()
        if sub == 'help':
            return self._build_help_text()
        if sub == 'version':
            return f'KaivosAI version {VERSION}'
        if sub == 'pause':
            if self.clock:
                self.clock.pause()
            return 'Clock paused'
        if sub == 'resume':
            if self.clock:
                self.clock.start()
            return 'Clock resumed'
        if sub == 'optimize':
            all_objects = [o for o in self.game_map.cells.values()
                           if isinstance(o, (Robot, Mine, Storage, Base))]
            objects = sorted(all_objects, key=lambda o: o.id)
            old_ids = [o.id for o in objects]
            count = 0

            for new_id, obj in enumerate(objects, start=1):
                if obj.id != new_id:
                    obj.id = new_id
                    count += 1

            if count > 0 and self.conn:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM game_objects")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='game_objects'")
                self.conn.commit()

                for obj in self.game_map.cells.values():
                    if isinstance(obj, (Robot, Mine, Storage, Base)):
                        persist_object(self.conn, obj)

                game_seconds = self.clock.seconds if self.clock else 0
                log_event(self.conn, game_seconds, 'system',
                         f'Optimized {count} object IDs: {old_ids} -> [1..{len(objects)}]', None, None)
                return f'Optimized {count} object IDs to sequential order (1,2,3...). Total objects with IDs: {len(objects)}'
            return f'Object IDs are already optimized (1..{len(objects)})'

        return f"Unknown system command: {sub}"

    def _handle_map(self, parts: list) -> str:
        import os
        import random
        import time
        from .models import Mine, Storage, Base, Robot, create_object

        if len(parts) < 2:
            return 'See Map panel'
        sub = parts[1]

        if sub == 'terrain':
            density = 0.05
            cluster_size = 3
            if len(parts) >= 3:
                try:
                    density = float(parts[2])
                    if not 0.0 <= density <= 1.0:
                        return 'Density must be between 0.0 and 1.0'
                except ValueError:
                    return 'Density must be a number'
            if len(parts) >= 4:
                try:
                    cluster_size = int(parts[3])
                    if cluster_size < 1:
                        return 'Cluster size must be at least 1'
                except ValueError:
                    return 'Cluster size must be a number'
            try:
                border, terrain = self.game_map.generate_full_terrain(density, cluster_size)
                return f'Terrain generated: {border} border rocks, {terrain} interior rocks'
            except (MapError, ValueError) as e:
                return f'Terrain generation failed: {e}'
        if sub == 'demo':
            seed_value = int(time.time() * 1000000) + int.from_bytes(os.urandom(4), 'big')
            random.seed(seed_value)

            free_positions = []
            for x in range(1, 31):
                for y in range(1, 31):
                    if self.game_map.get((x, y)) is None:
                        free_positions.append((x, y))

            if len(free_positions) < 4:
                return 'Not enough free space for demo objects!'

            random.shuffle(free_positions)
            positions = free_positions[:4]

            demo_objects = [
                ('mine', None, 'Iron Mine', positions[0], {'durability': 25}),
                ('storage', None, 'Storage A', positions[1], {'capacity': 50}),
                ('base', None, 'Base', positions[2], {}),
                ('robot', None, 'Bot', positions[3], {'capacity': 5}),
            ]
            added = 0
            for typ, oid, name, pos, kwargs in demo_objects:
                try:
                    obj = create_object(typ, oid, name=name, pos=pos, **kwargs)
                    self.game_map.remove_object(pos)
                    self.game_map.add_object(obj, pos)
                    added += 1
                except (CommandError, MapError, ValueError):
                    pass
            return f'Added {added} demo objects at random positions'
        if sub == 'reset':
            for pos in list(self.game_map.cells.keys()):
                self.game_map.remove_object(pos)
            if self.game_map.conn:
                try:
                    self.game_map.conn.execute("DELETE FROM sqlite_sequence WHERE name='game_objects'")
                    self.game_map.conn.commit()
                except Exception:
                    pass
            if self.clock:
                self.clock.reset()
            return 'Everything reset: map cleared, clock reset'

        return f"Unknown map command: {sub}. Try: terrain, demo, reset"

    def _handle_create(self, parts: list) -> str:
        from .models import create_object

        if len(parts) < 4:
            return 'Usage: create TYPE X Y (e.g. create robot 5 7)'

        typ = parts[1]
        try:
            x = int(parts[2])
            y = int(parts[3])
        except (ValueError, IndexError):
            return 'Coordinates must be numbers'

        try:
            obj = create_object(typ, None, pos=(x, y))
            self.game_map.add_object(obj, (x, y))
            return f'Created {typ} at ({x},{y})'
        except Exception as e:
            return f'Error: {e}'

    def _handle_delete(self, parts: list) -> str:
        if len(parts) < 2:
            return 'Usage: remove at X Y  or  remove ID'

        if parts[1] in ('at', 'pos', 'position'):
            if len(parts) < 4:
                return 'Usage: remove at X Y'
            try:
                x = int(parts[2])
                y = int(parts[3])
            except ValueError:
                return 'Coordinates must be numbers'
            obj = self.game_map.remove_object((x, y))
            return f'Removed {type(obj).__name__ if obj else "nothing"}'

        if parts[1] in ('id', 'object', '#'):
            if len(parts) < 3:
                return 'Usage: remove id NUMBER'
            try:
                oid = int(parts[2])
            except ValueError:
                return 'ID must be a number'
            obj = self.game_map.remove_object(oid)
            return f'Removed {type(obj).__name__ if obj else "nothing"}'

        try:
            val = int(parts[1])
            if len(parts) == 2:
                obj = self.game_map.remove_object(val)
                return f'Removed {type(obj).__name__ if obj else "nothing"}'
            y = int(parts[2])
            obj = self.game_map.remove_object((val, y))
            return f'Removed {type(obj).__name__ if obj else "nothing"}'
        except ValueError:
            return 'Invalid coordinates or ID'

    def _handle_move(self, parts: list) -> str:
        if 'from' in parts:
            from_idx = parts.index('from')
            to_idx = parts.index('to') if 'to' in parts else -1
            if to_idx < 0 or to_idx - from_idx != 3:
                return 'Usage: move from X Y to X Y'
            try:
                x1 = int(parts[from_idx + 1])
                y1 = int(parts[from_idx + 2])
                x2 = int(parts[to_idx + 1])
                y2 = int(parts[to_idx + 2])
            except (ValueError, IndexError):
                return 'Coordinates must be numbers'
        elif 'to' in parts:
            to_idx = parts.index('to')
            if to_idx != 3:
                return 'Usage: move X Y to X Y'
            try:
                x1 = int(parts[1])
                y1 = int(parts[2])
                x2 = int(parts[to_idx + 1])
                y2 = int(parts[to_idx + 2])
            except (ValueError, IndexError):
                return 'Coordinates must be numbers'
        else:
            if len(parts) < 5:
                return 'Usage: move X Y to X Y'
            try:
                x1 = int(parts[1])
                y1 = int(parts[2])
                x2 = int(parts[3])
                y2 = int(parts[4])
            except ValueError:
                return 'Coordinates must be numbers'

        try:
            self.game_map.move_object((x1, y1), (x2, y2))
            return f'Moved from ({x1},{y1}) to ({x2},{y2})'
        except Exception as e:
            return f'Error: {e}'

    def _handle_inspect(self, parts: list) -> str:
        if len(parts) < 3:
            return 'Usage: inspect X Y'
        try:
            x = int(parts[1])
            y = int(parts[2])
        except (ValueError, IndexError):
            return 'Coordinates must be numbers'
        obj = self.game_map.get((x, y))
        if obj:
            name = getattr(obj, 'name', type(obj).__name__)
            return f'{name} at ({x},{y})'
        return f'Nothing at ({x},{y})'

    def _handle_robot_load(self, robot: 'Robot', rid: int, parts: list) -> str:
        from .models import Robot, Mine, Storage, Base
        from .db import persist_object

        adjacent = self.game_map.get_adjacent_objects(robot.pos)
        valid = [o for o in adjacent if isinstance(o, (Mine, Storage, Base, Robot)) and o != robot]
        if len(valid) == 0:
            return 'No adjacent objects to load from (need Mine, Storage, Base, or Robot nearby)'
        if len(valid) > 1:
            return f'Multiple adjacent objects ({len(valid)}). Move robot to have only one adjacent object.'

        source = valid[0]
        amount = None
        if len(parts) >= 4:
            try:
                amount = int(parts[3])
            except ValueError:
                pass

        robot.start_loading(source, amount)

        if self.conn:
            persist_object(self.conn, robot)
            game_seconds = self.clock.seconds if self.clock else 0
            source_name = getattr(source, 'name', type(source).__name__)
            log_event(self.conn, game_seconds, 'robot_loading',
                     f'Robot {rid} started loading from {source_name} at ({robot.pos[0]},{robot.pos[1]})', robot, robot.pos)

        source_name = getattr(source, 'name', type(source).__name__)
        transfer_amount = amount if amount is not None else (robot.capacity - robot.inventory)
        return f'Robot {rid} started loading {transfer_amount} material from {source_name} (1/s). Inventory: {robot.inventory}/{robot.capacity}'

    def _handle_robot_unload(self, robot: 'Robot', rid: int, parts: list) -> str:
        from .models import Storage, Base, Robot
        from .db import persist_object

        adjacent = self.game_map.get_adjacent_objects(robot.pos)
        valid = [o for o in adjacent if isinstance(o, (Storage, Base, Robot)) and o != robot]
        if len(valid) == 0:
            return 'No adjacent objects to unload to (need Storage, Base, or Robot nearby)'
        if len(valid) > 1:
            return f'Multiple adjacent objects ({len(valid)}). Move robot to have only one adjacent object.'

        target = valid[0]
        amount = None
        if len(parts) >= 4:
            try:
                amount = int(parts[3])
            except ValueError:
                pass

        robot.start_unloading(target, amount)

        if self.conn:
            persist_object(self.conn, robot)
            game_seconds = self.clock.seconds if self.clock else 0
            target_name = getattr(target, 'name', type(target).__name__)
            log_event(self.conn, game_seconds, 'robot_unloading',
                     f'Robot {rid} started unloading to {target_name} at ({robot.pos[0]},{robot.pos[1]})', robot, robot.pos)

        target_name = getattr(target, 'name', type(target).__name__)
        transfer_amount = amount if amount is not None else robot.inventory
        return f'Robot {rid} started unloading {transfer_amount} material to {target_name} (1/s). Inventory: {robot.inventory}/{robot.capacity}'

    def _handle_robot_program(self, robot: 'Robot', rid: int, parts: list) -> str:
        from .db import persist_object
        from .robobrain import RoboBASICParser

        action = parts[2] if len(parts) >= 3 else None

        if action in ('code', 'program', 'prg', 'prog', 'edit'):
            if self.show_command_editor:
                self.show_command_editor(robot)
                return f'Editing code for {robot.name}'
            return 'Program editor unavailable in this mode'

        if action in ('start', 'run', 'execute', 's'):
            parsed, labels, errors = RoboBASICParser.parse_program(robot.commands_text)

            if errors:
                error_msg = '; '.join(errors[:3])
                return f'Cannot start program: {error_msg}'

            # Reset execution state so starting always begins from line 0 and
            # cancels any pending movement or transfer.
            robot._move_path = None
            robot._move_target = None
            robot._move_stop_distance = 0
            robot._loading_from = None
            robot._loading_amount = None
            robot._unloading_to = None
            robot._unloading_amount = None
            robot._parsed_program = parsed
            robot._program_labels = labels
            robot._program_running = True
            robot._program_counter = 0
            robot._blocked_until = 0.0

            if self.conn:
                persist_object(self.conn, robot)
                game_seconds = self.clock.seconds if self.clock else 0
                log_event(self.conn, game_seconds, 'robot_program',
                         f'Robot {rid} code started', robot, robot.pos)

            return f'Robot {rid} code started (RoboBRAIN active)'

        if action in ('pause', 'halt', 'stop', 'end', 'p'):
            robot._program_running = False

            if self.conn:
                persist_object(self.conn, robot)
                game_seconds = self.clock.seconds if self.clock else 0
                log_event(self.conn, game_seconds, 'robot_program',
                         f'Robot {rid} code paused', robot, robot.pos)

            return f'Robot {rid} code paused'

        return 'Unknown program action'

    def _handle_robot_movement(self, robot: 'Robot', rid: int, parts: list) -> str:
        from .models import Robot

        offset = 2
        if parts[2] in ('go', 'goto', 'g', 'move', 'm', 'walk'):
            offset = 3
        if offset < len(parts) and parts[offset] == 'to':
            offset += 1

        stop_distance = 0
        distance_keyword_idx = -1

        for i in range(offset, len(parts)):
            if parts[i] in ('distance', 'dist', 'd'):
                distance_keyword_idx = i
                break

        if distance_keyword_idx >= 0:
            if distance_keyword_idx + 1 < len(parts):
                try:
                    stop_distance = int(parts[distance_keyword_idx + 1])
                except ValueError:
                    return 'Distance must be a number'
            else:
                return 'Distance keyword requires a number'

        param_count = (distance_keyword_idx - offset) if distance_keyword_idx >= 0 else (len(parts) - offset)

        if param_count == 1:
            try:
                target_id = int(parts[offset])
            except ValueError:
                return 'Object ID must be a number'

            target_obj = None
            for obj in self.game_map.cells.values():
                if getattr(obj, 'id', None) == target_id:
                    target_obj = obj
                    break

            if not target_obj:
                return f'Object {target_id} not found'

            if isinstance(target_obj, Robot):
                return 'Cannot target robots. Use coordinates or target Mine/Storage/Base.'

            x, y = target_obj.pos

            if stop_distance == 0:
                stop_distance = 1

        elif param_count >= 2:
            try:
                x = int(parts[offset])
                y = int(parts[offset + 1])
            except (ValueError, IndexError):
                return 'Coordinates must be numbers'
        else:
            return 'Usage: robot ID go to X Y [distance N] or robot ID go to OBJ_ID [distance N]'

        try:
            started = self.game_map.command_move_robot(rid, (x, y), stop_distance)
            if started:
                if self.conn:
                    game_seconds = self.clock.seconds if self.clock else 0
                    name = getattr(robot, 'name', f'Robot {rid}')
                    dist_msg = f' (stop {stop_distance} cells away)' if stop_distance > 0 else ''
                    log_event(self.conn, game_seconds, 'robot_moving',
                             f'{name} started moving to ({x},{y}){dist_msg} from ({robot.pos[0]},{robot.pos[1]})', robot, robot.pos)
                dist_text = f' (stopping {stop_distance} cells away)' if stop_distance > 0 else ''
                return f'Robot {rid} moving to ({x},{y}){dist_text}'
            return 'No path available or already at target'
        except Exception as e:
            return f'Error: {e}'

    def _handle_robot(self, parts: list) -> str:
        from .models import Robot

        if len(parts) < 2:
            return 'Usage: robot ID <command>'
        try:
            rid = int(parts[1])
        except ValueError:
            return 'Robot ID must be a number'

        robot = None
        for obj in self.game_map.cells.values():
            if isinstance(obj, Robot) and getattr(obj, 'id', None) == rid:
                robot = obj
                break

        if not robot:
            return f'Robot {rid} not found'

        if len(parts) >= 3:
            action = parts[2]

            if action in ('load', 'take', 'pickup', 'get'):
                return self._handle_robot_load(robot, rid, parts)
            if action in ('unload', 'dump', 'drop', 'put', 'store'):
                return self._handle_robot_unload(robot, rid, parts)
            if action in ('code', 'program', 'prg', 'prog', 'edit', 'start', 'run', 'execute', 's', 'pause', 'halt', 'stop', 'end', 'p'):
                return self._handle_robot_program(robot, rid, parts)
            if action in ('go', 'goto', 'g', 'move', 'm', 'walk'):
                return self._handle_robot_movement(robot, rid, parts)

        if len(parts) >= 4:
            return self._handle_robot_movement(robot, rid, parts)

        return 'Usage: robot ID <load|unload|code|start|pause|goto X Y>'

    def process_command(self, cmd_line: str):
        if not cmd_line:
            return ""

        try:
            parts = shlex.split(cmd_line.lower())
        except Exception:
            parts = cmd_line.lower().split()

        if not parts:
            return ""

        parts = expand_aliases(parts)
        first = parts[0]

        handlers = {
            'system': self._handle_system,
            'map': self._handle_map,
            'create': self._handle_create,
            'delete': self._handle_delete,
            'move': self._handle_move,
            'goto': self._handle_move,
            'inspect': self._handle_inspect,
            'robot': self._handle_robot,
            'bot': self._handle_robot,
            'r': self._handle_robot,
        }

        if first in handlers:
            return handlers[first](parts)

        if first == 'quit':
            import urwid
            raise urwid.ExitMainLoop()

        if first == 'help':
            return self._build_help_text()

        if first == 'version':
            return f'KaivosAI version {VERSION}'

        if first == 'pause':
            if self.clock:
                self.clock.pause()
            return 'Clock paused'

        if first == 'resume':
            if self.clock:
                self.clock.start()
            return 'Clock resumed'

        if first == 'terrain':
            return 'Use "map terrain [density] [size]" or "map t" instead'

        if first == 'list':
            return 'See Objects panel (or use "map list")'

        if first == 'reset':
            return 'Use "map reset" instead'

        if first == 'demo':
            return 'Use "map demo" instead'

        return f"I don't understand '{cmd_line}'. Type 'help' or 'system help' for commands."

class CommandEdit(urwid.Edit):
    """Edit widget with tab completion support."""
    
    def __init__(self, *args, **kwargs):
        """Initialize edit widget and tab completion state."""
        super().__init__(*args, **kwargs)
        self.completions = COMPLETIONS
        self.completion_index = -1
        self.original_text = ""
    
    def keypress(self, size, key):
        """Handle Tab-based completions; delegate other keys to parent.

        Starts a completion cycle on first Tab for the last word,
        cycles through matches on subsequent Tabs, and resets the
        cycle on any non-Tab key.
        """
        if key == 'tab':
            text = self.get_edit_text()
            
            # Start new completion cycle
            if self.completion_index == -1:
                self.original_text = text
                words = text.split()
                if not words:
                    return
                
                # Get last word for completion
                last_word = words[-1] if words else ""
                prefix = " ".join(words[:-1]) + (" " if len(words) > 1 else "")
                
                # Find matching completions
                matches = [c for c in self.completions if c.startswith(last_word)]
                
                if matches:
                    self.completion_matches = matches
                    self.completion_prefix = prefix
                    self.completion_index = 0
                    self.set_edit_text(prefix + matches[0])
                    self.set_edit_pos(len(self.get_edit_text()))
            else:
                # Cycle through matches
                self.completion_index = (self.completion_index + 1) % len(self.completion_matches)
                self.set_edit_text(self.completion_prefix + self.completion_matches[self.completion_index])
                self.set_edit_pos(len(self.get_edit_text()))
            
            return
        else:
            # Reset completion on any other key
            self.completion_index = -1
            return super().keypress(size, key)


def expand_aliases(parts: List[str]) -> List[str]:
    """Expand command aliases to their full form.
    
    Args:
        parts: List of command tokens
        
    Returns:
        List with aliases expanded (e.g., ['r', 'goto'] -> ['robot', 'goto'])
        
    Note:
        Preserves unknown tokens unchanged. See COMMAND_ALIASES for mappings.
    """
    if not parts:
        return []

    first = COMMAND_ALIASES.get(parts[0], parts[0])

    # Apply context-aware aliases for robot commands so short forms like
    # "r ID c" map to "robot ID code" without colliding with create.
    if first in ('robot', 'bot', 'r', 'rob'):
        normalized = ['robot']

        if len(parts) >= 2:
            normalized.append(parts[1])

        for token in parts[2:]:
            normalized.append(ROBOT_ACTION_ALIASES.get(token, token))

        return normalized

    # Default path: expand each token independently
    return [first] + [COMMAND_ALIASES.get(p, p) for p in parts[1:]]


def run_urwid_tui(game_map: Map, clock: GameClock, conn):
    """Run the Urwid-based terminal UI with map, objects, events, and commands.
    
    Args:
        game_map: Game world with objects and spatial state
        clock: Background game clock for time progression
        conn: Database connection for persistence
        
    Note:
        - Creates Urwid main loop with 0.5s refresh rate
        - Defines color palette for objects, status, events
        - Builds UI with map display (left), object list + events (right)
        - Command input at bottom with echo/result display
        - Auto-centers map on objects
        - Tick rate: 0.5s for all game systems (movement, production, transfers, programs)
        - Exit with 'quit' command or Ctrl+C
    """
    
    # Define color palette with rich colors
    palette = [
        # Object colors (bright)
        ('robot', 'light cyan', 'default'),
        ('mine', 'yellow', 'default'),
        ('storage', 'light green', 'default'),
        ('base', 'light magenta', 'default'),
        ('rock', 'dark gray', 'default'),
        ('empty', 'black', 'default'),
        
        # Status colors
        ('success', 'light green', 'default'),
        ('warning', 'yellow', 'default'),
        ('error', 'light red', 'default'),
        ('info', 'light blue', 'default'),
        ('dim', 'dark gray', 'default'),
        
        # Object status (with background)
        ('robot_full', 'black', 'light cyan'),
        ('robot_empty', 'dark cyan', 'default'),
        ('mine_full', 'black', 'yellow'),
        ('mine_empty', 'dark red', 'default'),
        ('storage_full', 'black', 'light green'),
        ('storage_empty', 'dark green', 'default'),
        ('base_full', 'black', 'light magenta'),
        ('base_empty', 'dark magenta', 'default'),
        
        # Event type colors
        ('event_good', 'light green', 'default'),
        ('event_bad', 'light red', 'default'),
        ('event_neutral', 'white', 'default'),
        ('event_time', 'dark cyan', 'default'),
        
        # UI elements
        ('version_banner', 'black', 'light green'),
        ('title', 'light blue,bold', 'default'),
        ('border', 'dark cyan', 'default'),
    ]
    
    # Widgets
    map_text = urwid.Text('', align='left')
    object_list_text = urwid.Text('', align='left')
    events_text = urwid.Text('', align='left')
    clock_text = urwid.Text('', align='left')
    status_text = urwid.Text('', align='left')
    command_input = CommandEdit('> ')
    
    # Layout: map on left, object list + clock + events on right, status + input at bottom
    map_box = urwid.LineBox(urwid.Filler(map_text, valign='top'), title='Map')
    info_pile = urwid.Pile([
        urwid.LineBox(clock_text, title=f'Clock - KaivosAI v{VERSION}'),
        urwid.LineBox(urwid.Filler(object_list_text, valign='top'), title='Objects'),
        urwid.LineBox(urwid.Filler(events_text, valign='top'), title='Events (recent)'),
    ])
    top_columns = urwid.Columns([
        ('weight', 2, map_box),
        ('weight', 1, info_pile),
    ])
    
    main_pile = urwid.Pile([
        ('weight', 1, top_columns),
        ('pack', urwid.LineBox(status_text, title='Status')),
        ('pack', urwid.LineBox(command_input, title='Command (help, quit)')),
    ])
    
    # Editor state: track which robot's commands are being edited
    editor_state = {'robot': None, 'overlay': None}
    # Keep reference to the main unhandled input handler so debug dialogs can restore it
    main_unhandled_input = None
    
    def show_command_editor(robot):
        """Show modal RoboBASIC code editor for robot.
        
        Args:
            robot: Robot object to edit program for
            
        Note:
            - Displays 10-line editor (max 15 chars per line)
            - Shows syntax validation errors with line numbers
            - F2: Save and validate program
            - ESC: Cancel without saving
            - Cannot edit while program is running (must stop first)
            - Uses RoboBASICParser for syntax validation
            - Saves to robot.commands_text (list of strings)
        """
        if editor_state['robot'] is not None:
            return  # Already editing another robot
        
        # Check if robot code is running
        if hasattr(robot, '_program_running') and robot._program_running:
            status_text.set_text(f'Cannot edit: Robot {robot.id} code is running. Pause it first with: robot {robot.id} pause')
            return
        
        editor_state['robot'] = robot
        
        # Initialize commands_text if needed
        if not hasattr(robot, 'commands_text') or robot.commands_text is None:
            robot.commands_text = [''] * 10
        
        # Create text content from robot commands (10 lines)
        lines = []
        for i, line in enumerate(robot.commands_text[:10]):
            lines.append(urwid.Edit('', line[:15] if line else '', multiline=False))
        
        editor_pile = urwid.Pile(lines)
        editor_filler = urwid.Filler(editor_pile, valign='top')
        
        # Instructions
        instructions = urwid.Text([
            ('info', 'Arrow keys: navigate | '),
            ('event_good', 'F2: Save | '),
            ('event_bad', 'ESC: Cancel')
        ])
        
        editor_box = urwid.LineBox(
            urwid.Pile([
                ('weight', 1, editor_filler),
                ('pack', urwid.Divider('-')),
                ('pack', instructions),
            ]),
            title=f"Commands: {robot.name} (ID {robot.id}) - 10 lines x 20 chars"
        )
        
        # Create overlay widget
        overlay_widget = urwid.Overlay(
            editor_box,
            main_pile,
            align='center',
            width=('relative', 60),
            valign='middle',
            height=('relative', 60),
        )
        
        def editor_keypress(widget, size, key):
            """Handle editor keystrokes."""
            if key == 'esc':
                # Cancel editing
                editor_state['robot'] = None
                editor_state['overlay'] = None
                loop.widget = main_pile
                status_text.set_text('Command editing cancelled')
                return True
            elif key == 'f2':
                # Save changes - first validate syntax
                from .robobrain import RoboBASICParser
                
                # Collect edited text
                edited_lines = []
                for i, edit_widget in enumerate(lines):
                    text = edit_widget.get_edit_text()
                    # Truncate to 20 chars
                    robot.commands_text[i] = text[:20]
                    edited_lines.append(text[:20])
                
                # Parse and validate program
                parsed, labels, errors = RoboBASICParser.parse_program(edited_lines)
                
                if errors:
                    # Show debug dialog with syntax errors
                    show_debug_dialog('SYNTAX ERRORS', errors)
                    # Don't save, don't close editor
                    return True
                
                # Valid program - store parsed version
                robot._parsed_program = parsed
                robot._program_labels = labels
                
                # Persist to database
                if conn:
                    from .db import persist_object
                    persist_object(conn, robot)
                
                editor_state['robot'] = None
                editor_state['overlay'] = None
                loop.widget = main_pile
                status_text.set_text(f'Commands saved for {robot.name}')
                return True
            elif key == 'up':
                # Move to previous line
                try:
                    current_idx = lines.index(editor_pile.focus)
                    if current_idx > 0:
                        editor_pile.focus_position = current_idx - 1
                except (ValueError, AttributeError):
                    # Focus widget not in lines list or focus_position unavailable
                    pass
                return True
            elif key == 'down':
                # Move to next line
                try:
                    current_idx = lines.index(editor_pile.focus)
                    if current_idx < len(lines) - 1:
                        editor_pile.focus_position = current_idx + 1
                except (ValueError, AttributeError):
                    # Focus widget not in lines list or focus_position unavailable
                    pass
                return True
            else:
                # Pass other keys to default handler
                return widget._keypress(size, key)
        
        # Override keypress
        overlay_widget._keypress = overlay_widget.keypress
        overlay_widget.keypress = lambda size, key: editor_keypress(overlay_widget, size, key)
        
        editor_state['overlay'] = overlay_widget
        loop.widget = overlay_widget
    
    def build_map_display():
        """Build ASCII map display with colored objects and coordinates.
        
        Returns:
            List of (style, text) tuples for urwid.Text markup
            
        Note:
            - Auto-centers on objects (min/max positions + 2 cell margin)
            - Max display size: 120x60 (shows error if larger)
            - Coordinate labels: 3 rows (hundreds/tens/ones) at top, row labels on left
            - Object symbols: R=Robot, M=Mine, S=Storage, B=Base, K=Rock, .=Empty
            - Color coding: Objects highlighted, empty cells dim
            - Shows object capacity status (full/empty) with background colors
            - Legend at bottom with object counts
        """
        if not game_map.cells:
            minx = 0; miny = 0; maxx = 9; maxy = 9
        else:
            xs = [p[0] for p in game_map.cells.keys()]
            ys = [p[1] for p in game_map.cells.keys()]
            minx = max(0, min(xs) - 2)
            maxx = min(game_map.width - 1, max(xs) + 2)
            miny = max(0, min(ys) - 2)
            maxy = min(game_map.height - 1, max(ys) + 2)
        
        w = maxx - minx + 1
        h = maxy - miny + 1
        if w > 120 or h > 60:
            return [("Region too large (", f"{w}x{h})")]
        
        # Build markup list for colored text
        markup = []
        
        # Column labels in 3 rows: hundreds, tens, ones (for coordinates 0-999)
        # Row 1: Hundreds
        markup.append(('dim', '    '))
        for x in range(minx, maxx + 1):
            hundreds = (x // 100) % 10
            if hundreds > 0:
                markup.append(('info', str(hundreds)))
            else:
                markup.append(('dim', ' '))
            markup.append(' ')
        markup.append('\n')
        
        # Row 2: Tens
        markup.append(('dim', '    '))
        for x in range(minx, maxx + 1):
            tens = (x // 10) % 10
            if tens > 0 or x >= 10:
                markup.append(('info', str(tens)))
            else:
                markup.append(('dim', ' '))
            markup.append(' ')
        markup.append('\n')
        
        # Row 3: Ones
        markup.append(('dim', '    '))
        for x in range(minx, maxx + 1):
            markup.append(('info', str(x % 10)))
            markup.append(' ')
        markup.append('\n')
        
        # Separator line
        markup.append(('dim', '   +'))
        markup.append(('dim', '-' * (w * 2)))
        markup.append('\n')
        
        # Collect all robot paths for display
        path_positions = set()
        for pos, obj in game_map.cells.items():
            if isinstance(obj, Robot):
                path = getattr(obj, '_move_path', None)
                if path:
                    # Add all positions in the path to the set
                    path_positions.update(path)
        
        # Build grid with clear ASCII symbols and status colors
        for y in range(miny, maxy + 1):
            # Row label with separator (support 0-999)
            markup.append(('info', f"{y:3d}"))
            markup.append(('dim', '|'))
            
            for x in range(minx, maxx + 1):
                pos = (x, y)
                obj = game_map.get(pos)
                
                if obj is None:
                    # Check if this is part of a robot's path
                    if pos in path_positions:
                        markup.append(('dim', '··'))
                    else:
                        markup.append(('empty', '..'))
                elif isinstance(obj, Robot):
                    # Show robot with status-based color
                    if obj.inventory >= obj.capacity:
                        markup.append(('robot_full', 'R!'))
                    elif obj.inventory == 0:
                        markup.append(('robot_empty', 'R.'))
                    else:
                        markup.append(('robot', 'R '))
                elif isinstance(obj, Mine):
                    # Show mine with status
                    if obj.stored >= obj.capacity:
                        markup.append(('mine_full', 'M!'))
                    elif obj.stored == 0:
                        markup.append(('mine_empty', 'M.'))
                    else:
                        markup.append(('mine', 'M '))
                elif isinstance(obj, Storage):
                    # Show storage with status
                    if obj.stored >= obj.capacity:
                        markup.append(('storage_full', 'S!'))
                    elif obj.stored == 0:
                        markup.append(('storage_empty', 'S.'))
                    else:
                        markup.append(('storage', 'S '))
                elif isinstance(obj, Base):
                    # Show base with status
                    if obj.stored > 0:
                        markup.append(('base', 'B+'))
                    else:
                        markup.append(('base_empty', 'B.'))
                elif isinstance(obj, Rock):
                    markup.append(('rock', '##'))
                else:
                    markup.append('??')
            markup.append('\n')
        
        # Legend with clear symbols
        markup.append('\n')
        markup.append(('title', 'Legend: '))
        markup.append(('robot', 'R=Robot '))
        markup.append(('mine', 'M=Mine '))
        markup.append(('storage', 'S=Storage '))
        markup.append(('base', 'B=Base '))
        markup.append(('rock', '#=Rock '))
        markup.append('\n')
        markup.append(('dim', 'Status: '))
        markup.append(('success', '! =Full '))
        markup.append(('warning', '. =Empty '))
        markup.append(('info', '+ =Active'))
        
        return markup
    
    def build_object_list():
        """Build object list display with colors and status indicators.
        
        Returns:
            List of (style, text) tuples for urwid.Text markup
            
        Note:
            - Shows ID, name, position, and material/inventory status
            - Robot: Shows inventory (X/Y), target position if moving, transfer status, program status
            - Mine: Shows stored materials (X/Y)
            - Storage: Shows stored materials (X/Y)
            - Base: Shows bank materials
            - Rock: Shows position only
            - Color-coded by object type
            - Sorted by ID for consistent display
        """
        markup = []
        objects = sorted(game_map.cells.items(), key=lambda kv: (getattr(kv[1], 'id', 0) or 0))
        
        if not objects or all(isinstance(o[1], Rock) for o in objects):
            markup.append(('dim', 'No objects'))
            return markup
        
        for p, o in objects:
            # Skip rocks in object list
            if isinstance(o, Rock):
                continue
            oid = getattr(o, 'id', None)
            name = getattr(o, 'name', None) or type(o).__name__
            x, y = p
            
            # Use same symbols as map for consistency
            if isinstance(o, Robot):
                inventory = o.inventory
                capacity = o.capacity
                pct = int(inventory / capacity * 10) if capacity > 0 else 0
                
                if inventory >= capacity:
                    color = 'robot_full'
                    bar = '[' + '=' * 10 + ']'
                elif inventory == 0:
                    color = 'robot_empty'
                    bar = '[' + '.' * 10 + ']'
                else:
                    color = 'robot'
                    bar = '[' + '=' * pct + '.' * (10 - pct) + ']'
                
                # Check robot state (loading/unloading/moving/idle)
                state = ''
                # Show active program state even if robot is otherwise idle
                if getattr(o, '_program_running', False):
                    state = ' CODE'

                if hasattr(o, '_loading_from') and o._loading_from is not None:
                    state = ' LOADING'
                    color = 'robot'  # Active color
                elif hasattr(o, '_unloading_to') and o._unloading_to is not None:
                    state = ' UNLOADING'
                    color = 'robot'  # Active color
                elif hasattr(o, '_move_target') and o._move_target is not None:
                    state = ' MOVING'
                elif not state:
                    state = ' IDLE'
                
                markup.append((color, f"R {oid:2d} {name:10s}"))
                markup.append(('dim', f" @({x:2d},{y:2d}) "))
                markup.append((color, f"{bar} {inventory}/{capacity}"))
                markup.append(('dim', state))
                markup.append('\n')
                
            elif isinstance(o, Mine):
                stored = o.stored
                capacity = o.capacity
                pct = int(stored / capacity * 10) if capacity > 0 else 0
                
                if stored >= capacity:
                    color = 'mine_full'
                    bar = '[' + '=' * 10 + ']'
                elif stored == 0:
                    color = 'mine_empty'
                    bar = '[' + '.' * 10 + ']'
                else:
                    color = 'mine'
                    bar = '[' + '=' * pct + '.' * (10 - pct) + ']'
                
                markup.append((color, f"M {oid:2d} {name:10s}"))
                markup.append(('dim', f" @({x:2d},{y:2d}) "))
                markup.append((color, f"{bar} {stored}/{capacity}"))
                markup.append('\n')
                
            elif isinstance(o, Storage):
                stored = o.stored
                capacity = o.capacity
                pct = int(stored / capacity * 10) if capacity > 0 else 0
                
                if stored >= capacity:
                    color = 'storage_full'
                    bar = '[' + '=' * 10 + ']'
                elif stored == 0:
                    color = 'storage_empty'
                    bar = '[' + '.' * 10 + ']'
                else:
                    color = 'storage'
                    bar = '[' + '=' * pct + '.' * (10 - pct) + ']'
                
                markup.append((color, f"S {oid:2d} {name:10s}"))
                markup.append(('dim', f" @({x:2d},{y:2d}) "))
                markup.append((color, f"{bar} {stored}/{capacity}"))
                markup.append('\n')
                
            elif isinstance(o, Base):
                stored = o.stored
                capacity = 20  # Base default capacity (not stored in model, but standard)
                pct = int(stored / capacity * 10) if capacity > 0 else 0
                
                if stored >= capacity:
                    color = 'base_full'
                    bar = '[' + '=' * 10 + ']'
                elif stored == 0:
                    color = 'base_empty'
                    bar = '[' + '.' * 10 + ']'
                else:
                    color = 'base'
                    bar = '[' + '=' * pct + '.' * (10 - pct) + ']'
                
                markup.append((color, f"B {oid:2d} {name:10s}"))
                markup.append(('dim', f" @({x:2d},{y:2d}) "))
                markup.append((color, f"{bar} {stored}/{capacity}"))
                markup.append('\n')
        
        return markup
    
    def build_events_display():
        """Build recent events list with color-coded event types.
        
        Returns:
            List of (style, text) tuples for urwid.Text markup
            
        Note:
            - Shows last 15 events from game_events table
            - Timestamp format: W<week>D<day>HH:MM:SS
            - Color-coded by event type: Good (robot_loaded, mine_full), Bad (robot_blocked), Neutral (robot_arrived)
            - Shows position if available
            - Empty state: "No events yet"
        """
        if not conn:
            return [('dim', 'No database connection')]
        
        from .db import get_recent_events
        from .clock import GameClock
        
        try:
            events = get_recent_events(conn, limit=15)
            if not events:
                return [('dim', 'No events yet')]
            
            # Collapse consecutive identical state events to avoid spam (same type/id/message)
            collapsed = []
            for event in events:
                key = (event[3], event[1], event[4])  # event_type, object_id, message
                if collapsed and collapsed[-1]['key'] == key:
                    collapsed[-1]['count'] += 1
                else:
                    collapsed.append({'data': event, 'count': 1, 'key': key})

            markup = []
            for item in collapsed:
                event = item['data']
                repeat_count = item['count']
                timestamp, obj_id, obj_type, event_type, message, x, y = event
                # Format timestamp as W<n>D<n>HH:MM:SS
                weeks, remainder = divmod(int(timestamp), 7 * 24 * 3600)
                days, remainder = divmod(remainder, 24 * 3600)
                hours, remainder = divmod(remainder, 3600)
                minutes, seconds = divmod(remainder, 60)
                time_str = f"W{weeks+1}D{days+1}{hours:02d}:{minutes:02d}:{seconds:02d}"
                
                # Determine event severity label and color for readability
                if event_type in ('robot_arrived', 'robot_loaded', 'robot_unloaded', 'base_supplied'):
                    event_color = 'event_good'
                    severity = 'OK'
                elif event_type in ('robot_blocked', 'robot_empty', 'mine_empty', 'storage_empty', 'base_empty'):
                    event_color = 'event_bad'
                    severity = 'ISSUE'
                elif event_type in ('robot_full', 'mine_full', 'storage_full'):
                    event_color = 'warning'
                    severity = 'WARN'
                else:
                    event_color = 'event_neutral'
                    severity = 'INFO'
                
                # Add object type indicator using same letters as map
                if obj_type == 'robot':
                    obj_letter = 'R'
                    obj_color = 'robot'
                elif obj_type == 'mine':
                    obj_letter = 'M'
                    obj_color = 'mine'
                elif obj_type == 'storage':
                    obj_letter = 'S'
                    obj_color = 'storage'
                elif obj_type == 'base':
                    obj_letter = 'B'
                    obj_color = 'base'
                else:
                    obj_letter = ''
                    obj_color = 'dim'
                
                # Clean up message while keeping it readable
                import re
                msg = re.sub(r'\s*at\s*\(\d+,\d+\)', '', message)
                msg = msg.replace('started moving to', 'moving to')
                msg = msg.replace('started loading from', 'loading from')
                msg = msg.replace('started unloading to', 'unloading to')
                msg = msg.replace('finished loading from', 'loaded from')
                msg = msg.replace('finished unloading to', 'unloaded to')
                msg = msg.replace('inventory', 'inv')
                msg = msg.strip()
                if len(msg) > 48:
                    msg = msg[:45] + '...'

                if repeat_count > 1:
                    msg = f"{msg} x{repeat_count}"

                obj_label = obj_letter
                if obj_label and obj_id:
                    obj_label = f"{obj_label}{obj_id}"
                elif obj_label:
                    obj_label = f"{obj_label}"  # keep type even if id missing
                else:
                    obj_label = '--'

                markup.append(('event_time', time_str))
                markup.append(' ')
                markup.append((event_color, f"{severity:<5}"))
                markup.append(' ')
                markup.append((obj_color, f"{obj_label:<4}"))
                markup.append(' ')
                markup.append((event_color, msg))
                markup.append('\n')
            
            return markup
        except Exception as e:
            return [('error', f'Error: {e}')]
    
    # 2x3 block digit render (width=2, height=3) using simple segments
    _digit_segments = {
        '0': (1,1,1,0,1,1,1),  # top, ul, ur, mid, ll, lr, bot
        '1': (0,0,1,0,0,1,0),
        '2': (1,0,1,1,1,0,1),
        '3': (1,0,1,1,0,1,1),
        '4': (0,1,1,1,0,1,0),
        '5': (1,1,0,1,0,1,1),
        '6': (1,1,0,1,1,1,1),
        '7': (1,0,1,0,0,1,0),
        '8': (1,1,1,1,1,1,1),
        '9': (1,1,1,1,0,1,1),
    }

    def _render_digit(ch: str):
        """Render a single digit using compact box-drawing characters (width=3, height=5).
        Uses a 7-segment mapping: top, ul, ur, mid, ll, lr, bot.
        """
        if ch == ':':
            # Compact five-row colon; blink handled by caller
            return ['   ', ' · ', '   ', ' · ', '   ']
        top, ul, ur, mid, ll, lr, bot = _digit_segments.get(ch, (0, 0, 0, 0, 0, 0, 0))
        rows = []
        # Row 0: top segment or upper verticals
        if top:
            rows.append('┌─┐')
        else:
            left = '│' if ul else ' '
            right = '│' if ur else ' '
            rows.append(left + ' ' + right)
        # Row 1: upper verticals
        left = '│' if ul else ' '
        right = '│' if ur else ' '
        rows.append(left + ' ' + right)
        # Row 2: middle segment or verticals
        if mid:
            left = '│' if ul else ' '
            right = '│' if ur else ' '
            rows.append(left + '─' + right)
        else:
            left = '│' if ul else ' '
            right = '│' if ur else ' '
            rows.append(left + ' ' + right)
        # Row 3: lower verticals
        left = '│' if ll else ' '
        right = '│' if lr else ' '
        rows.append(left + ' ' + right)
        # Row 4: bottom segment or spaces
        if bot:
            rows.append('└─┘')
        else:
            rows.append('   ')
        return rows

    def build_clock_display():
        """Build clock display with week/day and time text only."""
        try:
            sec = clock.seconds
            hh = (sec % 86400) // 3600
            mm = (sec % 3600) // 60
            ss = sec % 60
            week = (sec // 86400) // 7 + 1
            day = (sec // 86400) % 7 + 1
            return f"W{week} D{day}  {hh:02d}:{mm:02d}:{ss:02d}"
        except (AttributeError, TypeError):
            # Clock not available or seconds invalid
            return "--:--:--"
    
    def show_version_dialog():
        """Show modal dialog for new version notification."""
        from pathlib import Path
        
        # Create dialog content
        banner = urwid.Text(('version_banner', ' NEW VERSION AVAILABLE '), align='center')
        message = urwid.Text('\nA new version of KaivosAI has been detected.\nPlease restart the application to load the new code.\n', align='center')
        instructions = urwid.Text('Press any key to quit', align='center')
        
        dialog_content = urwid.Pile([
            urwid.Divider(),
            banner,
            urwid.Divider(),
            message,
            instructions,
            urwid.Divider(),
        ])
        
        dialog = urwid.LineBox(urwid.Filler(dialog_content), title='Update Notification')
        overlay = urwid.Overlay(
            dialog,
            main_pile,
            align='center',
            width=('relative', 50),
            valign='middle',
            height=('relative', 30)
        )
        
        def handle_version_key(key):
            """Close update dialog and exit on any key press."""
            # Any key press: quit application
            flag_file = Path(__file__).parent.parent / "flag_new_version.lck"
            try:
                flag_file.unlink()  # Remove flag file
            except (OSError, FileNotFoundError):
                # File already deleted or inaccessible
                pass
            raise urwid.ExitMainLoop()
        
        loop.widget = overlay
        loop.unhandled_input = handle_version_key
    
    def show_debug_dialog(title, errors):
        """Show modal dialog for displaying debug messages (syntax errors, etc)."""
        # Format error list
        error_lines = []
        for error in errors:
            error_lines.append(('event_bad', f"• {error}\n"))
        
        # Create dialog content
        banner = urwid.Text(('event_bad', f' {title} '), align='center')
        error_text = urwid.Text(error_lines)
        error_walker = urwid.SimpleFocusListWalker([error_text])
        error_listbox = urwid.ListBox(error_walker)
        instructions = urwid.Text('\nPress ESC to close', align='center')
        
        dialog_content = urwid.Pile([
            urwid.Divider(),
            banner,
            urwid.Divider(),
            ('weight', 1, error_listbox),
            ('pack', instructions),
            urwid.Divider(),
        ])
        
        dialog = urwid.LineBox(dialog_content, title='Debug Output')
        overlay = urwid.Overlay(
            dialog,
            main_pile,
            align='center',
            width=('relative', 60),
            valign='middle',
            height=('relative', 50)
        )
        
        def handle_debug_key(key):
            """Close debug dialog on ESC or any key press."""
            # ESC or any key: close dialog
            if key == 'esc' or key:
                loop.widget = main_pile
                loop.unhandled_input = main_unhandled_input or handle_input
                return True
        
        loop.widget = overlay
        loop.unhandled_input = handle_debug_key
    
    def refresh_display(loop=None, user_data=None):
        """Update all display widgets and tick all game systems.
        
        Args:
            loop: Urwid main loop (optional)
            user_data: User data from alarm callback (unused)
            
        Note:
            - Called every 0.5s by urwid alarm
            - Ticks: movement, production, transfers, RoboBRAIN programs
            - Updates: map display, object list, events, clock
            - Checks for flag_new_version.lck (triggers restart dialog)
            - Re-schedules next refresh with loop.set_alarm_in(0.5)
        """
        # Check if version flag file exists (signals code reload)
        from pathlib import Path
        flag_file = Path(__file__).parent.parent / "flag_new_version.lck"
        if flag_file.exists():
            # Pause clock and show modal dialog
            clock.pause()
            status_text.set_text("New version detected! See dialog...")
            show_version_dialog()
            return  # Don't schedule next refresh
        
        # Advance robot movement each refresh (simple steady state)
        game_map.tick_movement()
        # Handle material production and consumption
        game_seconds = clock.seconds
        game_map.tick_production(game_seconds)
        # Handle robot material transfers (loading/unloading)
        game_map.tick_transfer(game_seconds)
        # Execute robot RoboBASIC programs
        game_map.tick_programs(game_seconds)
        map_text.set_text(build_map_display())
        object_list_text.set_text(build_object_list())
        events_text.set_text(build_events_display())
        clock_text.set_text(build_clock_display())
        if loop:
            loop.set_alarm_in(0.5, refresh_display)
    
    def _handle_system(parts: list) -> str:
        """Handle system commands: quit, help, version, pause, resume, optimize.
        
        Args:
            parts: Parsed command parts starting with 'system'
            
        Returns:
            Status message
        """
        from .models import Robot, Mine, Storage, Base
        from .db import persist_object
        
        if len(parts) < 2:
            return 'Usage: system <help|version|quit|pause|resume|optimize>'
        sub = parts[1]
        
        if sub == 'quit':
            raise urwid.ExitMainLoop()
        elif sub == 'help':
            return process_command('help')
        elif sub == 'version':
            return f'KaivosAI version {VERSION}'
        elif sub == 'pause':
            clock.pause()
            return 'Clock paused'
        elif sub == 'resume':
            clock.start()
            return 'Clock resumed'
        elif sub == 'optimize':
            all_objects = [o for o in game_map.cells.values() 
                          if isinstance(o, (Robot, Mine, Storage, Base))]
            objects = sorted(all_objects, key=lambda o: o.id)
            old_ids = [o.id for o in objects]
            count = 0
            
            for new_id, obj in enumerate(objects, start=1):
                if obj.id != new_id:
                    obj.id = new_id
                    count += 1
            
            if count > 0 and conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM game_objects")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='game_objects'")
                conn.commit()
                
                for obj in game_map.cells.values():
                    if isinstance(obj, (Robot, Mine, Storage, Base)):
                        persist_object(conn, obj)
                
                game_seconds = clock.seconds if clock else 0
                log_event(conn, game_seconds, 'system', 
                         f'Optimized {count} object IDs: {old_ids} -> [1..{len(objects)}]', None, None)
                return f'Optimized {count} object IDs to sequential order (1,2,3...). Total objects with IDs: {len(objects)}'
            else:
                return f'Object IDs are already optimized (1..{len(objects)})'
        else:
            return f"Unknown system command: {sub}"
    
    def _handle_map(parts: list) -> str:
        """Handle map commands: show, list, terrain, demo, reset.
        
        Args:
            parts: Parsed command parts starting with 'map'
            
        Returns:
            Status message
        """
        import os
        import random
        import time
        from .models import Mine, Storage, Base, Robot, create_object
        
        if len(parts) < 2:
            return 'See Map panel'
        sub = parts[1]
        
        if sub == 'show':
            return 'See Map panel'
        elif sub == 'list':
            return 'See Objects panel'
        elif sub == 'terrain':
            density = 0.05
            cluster_size = 3
            if len(parts) >= 3:
                try:
                    density = float(parts[2])
                    if not 0.0 <= density <= 1.0:
                        return 'Density must be between 0.0 and 1.0'
                except ValueError:
                    return 'Density must be a number'
            if len(parts) >= 4:
                try:
                    cluster_size = int(parts[3])
                    if cluster_size < 1:
                        return 'Cluster size must be at least 1'
                except ValueError:
                    return 'Cluster size must be a number'
            try:
                border, terrain = game_map.generate_full_terrain(density, cluster_size)
                return f'Terrain generated: {border} border rocks, {terrain} interior rocks'
            except (MapError, ValueError) as e:
                return f'Terrain generation failed: {e}'
        elif sub == 'demo':
            seed_value = int(time.time() * 1000000) + int.from_bytes(os.urandom(4), 'big')
            random.seed(seed_value)
            
            free_positions = []
            for x in range(1, 31):
                for y in range(1, 31):
                    if game_map.get((x, y)) is None:
                        free_positions.append((x, y))
            
            if len(free_positions) < 4:
                return 'Not enough free space for demo objects!'
            
            random.shuffle(free_positions)
            positions = free_positions[:4]
            
            demo_objects = [
                ('mine', None, 'Iron Mine', positions[0], {'durability': 25}),
                ('storage', None, 'Storage A', positions[1], {'capacity': 50}),
                ('base', None, 'Base', positions[2], {}),
                ('robot', None, 'Bot', positions[3], {'capacity': 5}),
            ]
            added = 0
            for typ, oid, name, pos, kwargs in demo_objects:
                try:
                    obj = create_object(typ, oid, name=name, pos=pos, **kwargs)
                    game_map.remove_object(pos)
                    game_map.add_object(obj, pos)
                    added += 1
                except (CommandError, MapError, ValueError):
                    # Object creation or placement failed, skip
                    pass
            return f'Added {added} demo objects at random positions'
        elif sub == 'reset':
            for pos in list(game_map.cells.keys()):
                game_map.remove_object(pos)
            if game_map.conn:
                try:
                    game_map.conn.execute("DELETE FROM sqlite_sequence WHERE name='game_objects'")
                    game_map.conn.commit()
                except Exception:
                    # Sequence table may not exist, ignore
                    pass
            clock.reset()
            return 'Everything reset: map cleared, clock reset'
        else:
            return f"Unknown map command: {sub}. Try: show, list, terrain, demo, reset"
    
    def _handle_create(parts: list) -> str:
        """Handle create object command.
        
        Args:
            parts: Parsed command parts starting with 'create'
            
        Returns:
            Status message
        """
        from .models import create_object
        
        if len(parts) < 4:
            return 'Usage: create TYPE X Y (e.g. create robot 5 7)'
        
        typ = parts[1]
        try:
            x = int(parts[2])
            y = int(parts[3])
        except (ValueError, IndexError):
            return 'Coordinates must be numbers'
        
        try:
            obj = create_object(typ, None, pos=(x, y))
            game_map.add_object(obj, (x, y))
            return f'Created {typ} at ({x},{y})'
        except Exception as e:
            return f'Error: {e}'
    
    def _handle_delete(parts: list) -> str:
        """Handle delete object command.
        
        Args:
            parts: Parsed command parts starting with 'delete'
            
        Returns:
            Status message
        """
        if len(parts) < 2:
            return 'Usage: remove at X Y  or  remove ID'
        
        if parts[1] in ('at', 'pos', 'position'):
            if len(parts) < 4:
                return 'Usage: remove at X Y'
            try:
                x = int(parts[2])
                y = int(parts[3])
            except ValueError:
                return 'Coordinates must be numbers'
            obj = game_map.remove_object((x, y))
            return f'Removed {type(obj).__name__ if obj else "nothing"}'
        
        if parts[1] in ('id', 'object', '#'):
            if len(parts) < 3:
                return 'Usage: remove id NUMBER'
            try:
                oid = int(parts[2])
            except ValueError:
                return 'ID must be a number'
            obj = game_map.remove_object(oid)
            return f'Removed {type(obj).__name__ if obj else "nothing"}'
        
        try:
            val = int(parts[1])
            if len(parts) == 2:
                obj = game_map.remove_object(val)
                return f'Removed {type(obj).__name__ if obj else "nothing"}'
            else:
                y = int(parts[2])
                obj = game_map.remove_object((val, y))
                return f'Removed {type(obj).__name__ if obj else "nothing"}'
        except ValueError:
            return 'Invalid coordinates or ID'
    
    def _handle_move(parts: list) -> str:
        """Handle move object command.
        
        Args:
            parts: Parsed command parts starting with 'move'
            
        Returns:
            Status message
        """
        if 'from' in parts:
            from_idx = parts.index('from')
            to_idx = parts.index('to') if 'to' in parts else -1
            if to_idx < 0 or to_idx - from_idx != 3:
                return 'Usage: move from X Y to X Y'
            try:
                x1 = int(parts[from_idx + 1])
                y1 = int(parts[from_idx + 2])
                x2 = int(parts[to_idx + 1])
                y2 = int(parts[to_idx + 2])
            except (ValueError, IndexError):
                return 'Coordinates must be numbers'
        elif 'to' in parts:
            to_idx = parts.index('to')
            if to_idx != 3:
                return 'Usage: move X Y to X Y'
            try:
                x1 = int(parts[1])
                y1 = int(parts[2])
                x2 = int(parts[to_idx + 1])
                y2 = int(parts[to_idx + 2])
            except (ValueError, IndexError):
                return 'Coordinates must be numbers'
        else:
            if len(parts) < 5:
                return 'Usage: move X Y to X Y'
            try:
                x1 = int(parts[1])
                y1 = int(parts[2])
                x2 = int(parts[3])
                y2 = int(parts[4])
            except ValueError:
                return 'Coordinates must be numbers'
        
        try:
            game_map.move_object((x1, y1), (x2, y2))
            return f'Moved from ({x1},{y1}) to ({x2},{y2})'
        except Exception as e:
            return f'Error: {e}'
    
    def _handle_inspect(parts: list) -> str:
        """Handle inspect position command.
        
        Args:
            parts: Parsed command parts starting with 'inspect'
            
        Returns:
            Status message
        """
        if len(parts) < 3:
            return 'Usage: inspect X Y'
        try:
            x = int(parts[1])
            y = int(parts[2])
        except (ValueError, IndexError):
            return 'Coordinates must be numbers'
        obj = game_map.get((x, y))
        if obj:
            name = getattr(obj, 'name', type(obj).__name__)
            return f'{name} at ({x},{y})'
        return f'Nothing at ({x},{y})'
    
    def _handle_robot_load(robot: 'Robot', rid: int, parts: list) -> str:
        """Handle robot load command.
        
        Args:
            robot: Robot object to load
            rid: Robot ID for logging
            parts: Command parts (parts[3] is optional amount)
            
        Returns:
            Status message
        """
        from .models import Robot, Mine, Storage, Base
        from .db import persist_object
        
        adjacent = game_map.get_adjacent_objects(robot.pos)
        valid = [o for o in adjacent if isinstance(o, (Mine, Storage, Base, Robot)) and o != robot]
        if len(valid) == 0:
            return 'No adjacent objects to load from (need Mine, Storage, Base, or Robot nearby)'
        if len(valid) > 1:
            return f'Multiple adjacent objects ({len(valid)}). Move robot to have only one adjacent object.'
        
        source = valid[0]
        amount = None
        if len(parts) >= 4:
            try:
                amount = int(parts[3])
            except ValueError:
                pass
        
        robot.start_loading(source, amount)
        
        if conn:
            persist_object(conn, robot)
            game_seconds = clock.seconds if clock else 0
            source_name = getattr(source, 'name', type(source).__name__)
            log_event(conn, game_seconds, 'robot_loading', 
                     f'Robot {rid} started loading from {source_name} at ({robot.pos[0]},{robot.pos[1]})', robot, robot.pos)
        
        source_name = getattr(source, 'name', type(source).__name__)
        transfer_amount = amount if amount is not None else (robot.capacity - robot.inventory)
        return f'Robot {rid} started loading {transfer_amount} material from {source_name} (1/s). Inventory: {robot.inventory}/{robot.capacity}'
    
    def _handle_robot_unload(robot: 'Robot', rid: int, parts: list) -> str:
        """Handle robot unload command.
        
        Args:
            robot: Robot object to unload
            rid: Robot ID for logging
            parts: Command parts (parts[3] is optional amount)
            
        Returns:
            Status message
        """
        from .models import Storage, Base, Robot
        from .db import persist_object
        
        adjacent = game_map.get_adjacent_objects(robot.pos)
        valid = [o for o in adjacent if isinstance(o, (Storage, Base, Robot)) and o != robot]
        if len(valid) == 0:
            return 'No adjacent objects to unload to (need Storage, Base, or Robot nearby)'
        if len(valid) > 1:
            return f'Multiple adjacent objects ({len(valid)}). Move robot to have only one adjacent object.'
        
        target = valid[0]
        amount = None
        if len(parts) >= 4:
            try:
                amount = int(parts[3])
            except ValueError:
                pass
        
        robot.start_unloading(target, amount)
        
        if conn:
            persist_object(conn, robot)
            game_seconds = clock.seconds if clock else 0
            target_name = getattr(target, 'name', type(target).__name__)
            log_event(conn, game_seconds, 'robot_unloading', 
                     f'Robot {rid} started unloading to {target_name} at ({robot.pos[0]},{robot.pos[1]})', robot, robot.pos)
        
        target_name = getattr(target, 'name', type(target).__name__)
        transfer_amount = amount if amount is not None else robot.inventory
        return f'Robot {rid} started unloading {transfer_amount} material to {target_name} (1/s). Inventory: {robot.inventory}/{robot.capacity}'
    
    def _handle_robot_program(robot: 'Robot', rid: int, parts: list) -> str:
        """Handle robot code editing and execution.
        
        Args:
            robot: Robot object
            rid: Robot ID for logging
            parts: Command parts (parts[2] determines action: code/start/pause)
            
        Returns:
            Status message
        """
        from .db import persist_object
        from .robobrain import RoboBASICParser
        
        action = parts[2] if len(parts) >= 3 else None
        
        # Edit code (auto-pause if running)
        if action in ('code', 'program', 'prg', 'prog', 'edit', 'c'):
            if getattr(robot, '_program_running', False):
                robot._program_running = False
                if conn:
                    persist_object(conn, robot)
                    game_seconds = clock.seconds if clock else 0
                    log_event(conn, game_seconds, 'robot_program',
                              f'Robot {rid} code paused for editing', robot, robot.pos)
                status_text.set_text(f'Robot {rid} code paused for editing')
            show_command_editor(robot)
            return f'Editing code for {robot.name}'
        
        # Start code execution
        if action in ('start', 'run', 'execute', 's'):
            parsed, labels, errors = RoboBASICParser.parse_program(robot.commands_text)
            
            if errors:
                error_msg = '; '.join(errors[:3])
                return f'Cannot start code: {error_msg}'
            
            robot._parsed_program = parsed
            robot._program_labels = labels
            robot._program_running = True
            robot._program_counter = 0
            robot._blocked_until = 0.0
            
            if conn:
                persist_object(conn, robot)
                game_seconds = clock.seconds if clock else 0
                log_event(conn, game_seconds, 'robot_program', 
                         f'Robot {rid} code started', robot, robot.pos)
            
            return f'Robot {rid} code started (RoboBRAIN active)'
        
        # Pause code execution
        if action in ('pause', 'halt', 'stop', 'end', 'p'):
            robot._program_running = False
            
            if conn:
                persist_object(conn, robot)
                game_seconds = clock.seconds if clock else 0
                log_event(conn, game_seconds, 'robot_program', 
                         f'Robot {rid} code paused', robot, robot.pos)
            
            return f'Robot {rid} code paused'
        
        return 'Unknown program action'
    
    def _handle_robot_movement(robot: 'Robot', rid: int, parts: list) -> str:
        """Handle robot movement command with pathfinding.
        
        Args:
            robot: Robot object to move
            rid: Robot ID for logging
            parts: Parsed command parts
            
        Returns:
            Status message
        """
        from .models import Robot
        
        offset = 2
        if parts[2] in ('go', 'goto', 'g', 'move', 'm', 'walk'):
            offset = 3
        if offset < len(parts) and parts[offset] == 'to':
            offset += 1
        
        stop_distance = 0
        distance_keyword_idx = -1
        
        for i in range(offset, len(parts)):
            if parts[i] in ('distance', 'dist', 'd'):
                distance_keyword_idx = i
                break
        
        if distance_keyword_idx >= 0:
            if distance_keyword_idx + 1 < len(parts):
                try:
                    stop_distance = int(parts[distance_keyword_idx + 1])
                except ValueError:
                    return 'Distance must be a number'
            else:
                return 'Distance keyword requires a number'
        
        param_count = (distance_keyword_idx - offset) if distance_keyword_idx >= 0 else (len(parts) - offset)
        
        if param_count == 1:
            try:
                target_id = int(parts[offset])
            except ValueError:
                return 'Object ID must be a number'
            
            target_obj = None
            for obj in game_map.cells.values():
                if getattr(obj, 'id', None) == target_id:
                    target_obj = obj
                    break
            
            if not target_obj:
                return f'Object {target_id} not found'
            
            if isinstance(target_obj, Robot):
                return 'Cannot target robots. Use coordinates or target Mine/Storage/Base.'
            
            x, y = target_obj.pos
            
            if stop_distance == 0:
                stop_distance = 1
                
        elif param_count >= 2:
            try:
                x = int(parts[offset])
                y = int(parts[offset + 1])
            except (ValueError, IndexError):
                return 'Coordinates must be numbers'
        else:
            return 'Usage: robot ID go to X Y [distance N] or robot ID go to OBJ_ID [distance N]'
        
        try:
            started = game_map.command_move_robot(rid, (x, y), stop_distance)
            if started:
                if conn:
                    game_seconds = clock.seconds if clock else 0
                    name = getattr(robot, 'name', f'Robot {rid}')
                    dist_msg = f' (stop {stop_distance} cells away)' if stop_distance > 0 else ''
                    log_event(conn, game_seconds, 'robot_moving', 
                             f'{name} started moving to ({x},{y}){dist_msg} from ({robot.pos[0]},{robot.pos[1]})', robot, robot.pos)
                dist_text = f' (stopping {stop_distance} cells away)' if stop_distance > 0 else ''
                return f'Robot {rid} moving to ({x},{y}){dist_text}'
            else:
                return 'No path available or already at target'
        except ValueError as e:
            return f'Error: {e}'
        except Exception as e:
            return f'Error: {e}'
    
    def _handle_robot(parts: list) -> str:
        """Handle robot command by dispatching to sub-handlers.
        
        Delegates to specialized handlers for different robot operations:
        - load: retrieve materials from adjacent objects
        - unload: deposit materials to adjacent objects
        - code/start/pause: manage RoboBASIC code execution
        - goto/movement: command pathfinding and movement
        
        Args:
            parts: Parsed command parts starting with 'robot'
            
        Returns:
            Status message
        """
        from .models import Robot
        
        if len(parts) < 2:
            return 'Usage: robot ID <command>'
        try:
            rid = int(parts[1])
        except ValueError:
            return 'Robot ID must be a number'
        
        robot = None
        for obj in game_map.cells.values():
            if isinstance(obj, Robot) and getattr(obj, 'id', None) == rid:
                robot = obj
                break
        
        if not robot:
            return f'Robot {rid} not found'
        
        # Dispatch to appropriate handler based on command
        if len(parts) >= 3:
            action = parts[2]
            
            if action in ('load', 'take', 'pickup', 'get'):
                return _handle_robot_load(robot, rid, parts)
            elif action in ('unload', 'dump', 'drop', 'put', 'store'):
                return _handle_robot_unload(robot, rid, parts)
            elif action in ('code', 'program', 'prg', 'prog', 'edit', 'start', 'run', 'execute', 's', 'pause', 'halt', 'stop', 'end', 'p'):
                return _handle_robot_program(robot, rid, parts)
            elif action in ('go', 'goto', 'g', 'move', 'm', 'walk'):
                return _handle_robot_movement(robot, rid, parts)
        
        # Movement commands (no explicit go/goto verb)
        if len(parts) >= 4:
            return _handle_robot_movement(robot, rid, parts)
        
        return 'Usage: robot ID <load|unload|code|start|pause|goto X Y>'
    
    def _build_help_text() -> str:
        """Build help text for command reference.
        
        Returns:
            Formatted help text with all available commands
        """
        return ("Commands (with shortcuts):\n"
                "\n"
                "ROBOT CONTROL:\n"
                "• robot ID goto X Y [d N] (r ID g X Y [d N]) - move robot to position (stop N cells away)\n"
                "• robot ID goto OBJ_ID [d N] (r ID g OBJ_ID [d N]) - move robot near object (stop N cells away)\n"
                "• robot ID load [amount] (r ID l [N]) - load N materials from adjacent object\n"
                "• robot ID unload [amount] (r ID u [N]) - unload N materials to adjacent object\n"
                "• robot ID code (r ID c) - edit robot code (F2=save, ESC=cancel)\n"
                "• robot ID start (r ID s) - start executing robot code\n"
                "• robot ID pause (r ID p) - pause robot code execution\n"
                "\n"
                "OBJECT MANAGEMENT:\n"
                "• create TYPE X Y (c TYPE X Y) - create object at position (types: robot, mine, storage, base)\n"
                "• delete ID (d ID) - remove object by ID\n"
                "• delete X Y (d X Y) - remove object at position\n"
                "• inspect X Y - inspect position (show what's there)\n"
                "\n"
                "MAP OPERATIONS:\n"
                "• map show (map/m) - show map (displayed in left panel)\n"
                "• map list (map ls) - show all objects (displayed in right panel)\n"
                "• map terrain [density] [size] (map t [D] [S]) - generate terrain\n"
                "  density: 0.0-1.0 (default 0.05), size: cluster size 1+ (default 3)\n"
                "• map demo (map demo) - add 4 demo objects at random positions\n"
                "• map reset (map reset) - clear map and reset clock\n"
                "\n"
                "SYSTEM COMMANDS:\n"
                "• system pause - pause clock (stops production/consumption)\n"
                "• system resume - resume clock\n"
                "• system optimize - renumber object IDs sequentially (1,2,3...)\n"
                "• system version - show KaivosAI version\n"
                "• system help - show this help text\n"
                "• system quit (quit) - exit game\n"
                "\n"
                "TIPS:\n"
                "• Use 'r' instead of 'robot', 'c' instead of 'create', 'd' instead of 'delete'\n"
                "• TAB for command completion\n"
                "• Program syntax: type 'help' while editing to see RoboBASIC commands")
    
    def process_command(cmd_line: str):
        """Process natural language command and return status message.
        
        Dispatches to handler functions based on first word (command name).
        
        Args:
            cmd_line: Command string to parse
            
        Returns:
            Status message string (success/error)
        
        Handler Functions:
            - _handle_system: quit, help, version, pause, resume, optimize
            - _handle_map: show, list, terrain, demo, reset
            - _handle_create: create objects
            - _handle_delete: delete objects
            - _handle_move: move objects
            - _handle_inspect: inspect positions
            - _handle_robot: movement, loading, unloading, programming
        
        Legacy standalone commands (for backward compatibility):
            - help, version, quit, pause, resume, terrain, list, inspect, reset, demo
        """
        if not cmd_line:
            return ""
        
        try:
            parts = shlex.split(cmd_line.lower())
        except Exception:
            parts = cmd_line.lower().split()
        
        if not parts:
            return ""
        
        parts = expand_aliases(parts)
        first = parts[0]
        
        # Dispatcher mapping: command -> handler function
        handlers = {
            'system': _handle_system,
            'map': _handle_map,
            'create': _handle_create,
            'delete': _handle_delete,
            'move': _handle_move,
            'inspect': _handle_inspect,
            'robot': _handle_robot,
            'bot': _handle_robot,
            'r': _handle_robot,
        }
        
        if first in handlers:
            return handlers[first](parts)
        
        # Legacy standalone commands
        if first == 'quit':
            raise urwid.ExitMainLoop()
        
        if first == 'help':
            return _build_help_text()
        
        if first == 'version':
            return f'KaivosAI version {VERSION}'
        
        if first == 'pause':
            clock.pause()
            return 'Clock paused'
        
        if first == 'resume':
            clock.start()
            return 'Clock resumed'
        
        # Legacy command redirects
        if first == 'terrain':
            return 'Use "map terrain [density] [size]" or "map t" instead'
        
        if first == 'list':
            return 'See Objects panel (or use "map list")'
        
        if first == 'reset':
            return 'Use "map reset" instead'
        
        if first == 'demo':
            return 'Use "map demo" instead'
        
        return f"I don't understand '{cmd_line}'. Type 'help' or 'system help' for commands."
    
    def handle_input(key):
        """Handle keyboard input."""
        if key == 'enter':
            cmd_line = command_input.get_edit_text()
            command_input.set_edit_text('')
            try:
                msg = process_command(cmd_line)
                status_text.set_text(f'> {cmd_line}\n{msg}')
                refresh_display()  # Refresh immediately after command
            except urwid.ExitMainLoop:
                raise
            except Exception as e:
                status_text.set_text(f'> {cmd_line}\nError: {e}')
        elif key in ('esc',):
            raise urwid.ExitMainLoop()

    # Store default unhandled input handler for restoring after modal dialogs
    main_unhandled_input = handle_input
    
    loop = urwid.MainLoop(main_pile, palette=palette, unhandled_input=handle_input)
    # Schedule immediate refresh after loop starts (0.01s delay ensures loop is running)
    loop.set_alarm_in(0.01, refresh_display)
    loop.run()


def run_demo():
    """Start the game with Urwid TUI and initialize demo world if needed.
    
    Creates:
        - 30x30 map with database persistence
        - GameClock background thread
        - Terrain generation (border + random rocks) if database empty
        - Demo objects (robots, mines, storage, bases) in random positions
        
    Note:
        - Entry point called from kaivosai.py
        - Database: databases/game.db (auto-created)
        - Only generates terrain/objects if database empty
        - Uses strong randomization: time.time() * 1e6 + os.urandom(4)
        - Rock density: 0.03 (3%), cluster size: 4
        - Launches Urwid TUI with run_urwid_tui()
    """
    conn = get_game_conn()
    init_game_db(conn)
    game_map = Map(width=30, height=30, conn=conn)
    # Start game clock (persistent)
    clock = GameClock(conn)
    clock.start()
    
    # Only add demo objects if database is empty
    existing = list(conn.execute('SELECT COUNT(*) as cnt FROM game_objects').fetchone())
    if existing[0] == 0:
        print("Empty database detected - generating terrain and adding demo objects...")
        
        # Use strong randomization: time with microseconds + OS random bytes
        seed_value = int(time.time() * 1000000) + int.from_bytes(os.urandom(4), 'big')
        random.seed(seed_value)
        print(f"Random seed: {seed_value}")
        
        # Generate terrain first
        border, terrain = game_map.generate_full_terrain(rock_density=0.03, cluster_size=4)
        print(f"Terrain generated: {border} border rocks, {terrain} terrain rocks")
        
        # Add demo objects in random positions within 30x30 area (IDs auto-assigned to avoid conflicts)
        # Find free positions (not occupied by rocks)
        free_positions = []
        for x in range(1, 31):
            for y in range(1, 31):
                if game_map.get((x, y)) is None:
                    free_positions.append((x, y))
        
        if len(free_positions) >= 4:
            random.shuffle(free_positions)
            positions = free_positions[:4]
            
            mine = Mine(name="Iron Mine", pos=positions[0], durability=25)
            storage = Storage(name="Storage A", pos=positions[1], capacity=50)
            base = Base(name="Base", pos=positions[2])
            bot = Robot(name="Bot", pos=positions[3], capacity=5)

            for obj in (mine, storage, base, bot):
                game_map.add_object(obj, obj.pos)
            print("Demo objects added. Use 'demo' command to recreate or 'reset' to clear.")
        else:
            print("Not enough free positions for demo objects!")

    # Launch Urwid TUI
    try:
        run_urwid_tui(game_map, clock, conn)
    finally:
        clock.stop()  # Stop immediately (no try/except to mask errors)
        conn.close()