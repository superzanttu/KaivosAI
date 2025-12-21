"""CLIController for command processing (UI-agnostic).

Provides natural language command parsing:
    - Object management: create, delete, move
    - Robot control: goto, load, unload, code/start/pause
    - Map operations: show, list, terrain, demo, reset
    - System: help, version, quit, pause, resume
    - Inspect: shows details about objects at coordinates

Key components:
    - CLIController: Command parser accepting game_map, clock, conn
    - process_command(): Natural language parser (~500 lines)
    - expand_aliases(): Maps short forms to full command names
    - _build_help_text(): Help text generation

Note:
    This module provides UI-agnostic command logic.
    The TUI rendering is handled by textual_cli.py (Textual framework).
    For testing: use CLIController directly without UI initialization.
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

# Note: Urwid UI removed - see textual_cli.py for TUI rendering

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

        if len(parts) < 2:
            return 'Usage: system <help|version|quit|pause|resume|optimize>'
        sub = parts[1]

        if sub == 'quit':
            # Quit is handled at UI level in textual_cli.py
            return 'Goodbye!'
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
            # Quit is handled at UI level
            return 'Goodbye!'

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


def expand_aliases(parts: List[str]) -> List[str]:
    """Expand command aliases to their full forms.
    
    Args:
        parts: Command parts (e.g. ['r', '1', 'g', '5', '10'])
        
    Returns:
        Expanded parts (e.g. ['robot', '1', 'goto', '5', '10'])
        
    Note:
        Primary command (parts[0]) expanded from COMMAND_ALIASES.
        Robot actions (after 'robot ID') expanded from ROBOT_ACTION_ALIASES.
    """
    if not parts:
        return parts
    
    result = parts.copy()
    
    # Expand primary command
    if result[0].lower() in COMMAND_ALIASES:
        result[0] = COMMAND_ALIASES[result[0].lower()]
    
    # If 'robot' command, expand robot-specific action aliases
    if result[0].lower() == 'robot' and len(result) >= 3:
        # parts[1] is robot ID, parts[2] is action
        action = result[2].lower()
        if action in ROBOT_ACTION_ALIASES:
            result[2] = ROBOT_ACTION_ALIASES[action]
    
    return result
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


# Note: Old Urwid TUI implementation removed - see textual_cli.py for modern TUI


def run_demo(db_path: str = "databases/game.db"):
    """Legacy entry point - redirects to Textual TUI.
    
    This function is kept for backward compatibility with old scripts.
    It simply calls run_textual_tui() from textual_cli.py.
    
    Args:
        db_path: Path to SQLite database (default: databases/game.db)
    """
    from .textual_cli import run_textual_tui
    run_textual_tui(db_path)
