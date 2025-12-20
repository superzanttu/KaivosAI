"""CLI and Urwid TUI for KaivosAI."""
from typing import Tuple, List
import shlex
import random
import time
import os

from .db import get_game_conn, init_game_db
from .map import Map
from .models import Robot, Mine, Storage, Base, Rock, create_object
from .clock import GameClock
from . import VERSION

Position = Tuple[int, int]

import urwid  # type: ignore


def run_urwid_tui(game_map: Map, clock: GameClock, conn):
    """Run the Urwid-based TUI with map, object list, clock and command input."""
    
    # Define color palette
    palette = [
        ('robot', 'light cyan', 'default'),
        ('mine', 'yellow', 'default'),
        ('storage', 'light green', 'default'),
        ('base', 'light magenta', 'default'),
        ('rock', 'dark gray', 'default'),
        ('empty', 'dark gray', 'default'),
    ]
    
    # Widgets
    map_text = urwid.Text('', align='left')
    object_list_text = urwid.Text('', align='left')
    clock_text = urwid.Text('', align='left')
    status_text = urwid.Text('', align='left')
    command_input = urwid.Edit('> ')
    
    # Layout: map on left, object list + clock on right, status + input at bottom
    map_box = urwid.LineBox(urwid.Filler(map_text, valign='top'), title='Map')
    info_pile = urwid.Pile([
        urwid.LineBox(clock_text, title=f'Clock - KaivosAI v{VERSION}'),
        urwid.LineBox(urwid.Filler(object_list_text, valign='top'), title='Objects'),
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
    
    def build_map_display():
        """Build ASCII map text with color markup."""
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
        
        # Column labels
        col_labels = '   ' + ' '.join(str(x % 10) for x in range(minx, maxx + 1)) + '\n'
        markup.append(col_labels)
        
        # Build grid with colors
        for y in range(miny, maxy + 1):
            # Row label
            markup.append(f"{y:2d} ")
            for x in range(minx, maxx + 1):
                obj = game_map.get((x, y))
                if obj is None:
                    markup.append(('empty', '. '))
                elif isinstance(obj, Robot):
                    markup.append(('robot', 'R '))
                elif isinstance(obj, Mine):
                    markup.append(('mine', 'M '))
                elif isinstance(obj, Storage):
                    markup.append(('storage', 'S '))
                elif isinstance(obj, Base):
                    markup.append(('base', 'B '))
                elif isinstance(obj, Rock):
                    markup.append(('rock', '# '))
                else:
                    markup.append('? ')
            markup.append('\n')
        
        markup.append('\nLegend: ')
        markup.append(('robot', 'R=Robot '))
        markup.append(('mine', 'M=Mine '))
        markup.append(('storage', 'S=Storage '))
        markup.append(('base', 'B=Base '))
        markup.append(('rock', '#=Rock'))
        
        return markup
    
    def build_object_list():
        """Build object list display."""
        lines: List[str] = []
        for p, o in sorted(game_map.cells.items(), key=lambda kv: (getattr(kv[1], 'id', 0) or 0)):
            # Skip rocks in object list
            if isinstance(o, Rock):
                continue
            oid = getattr(o, 'id', None)
            name = getattr(o, 'name', None) or type(o).__name__
            x, y = p
            
            # Show material storage info
            stored = getattr(o, 'stored', None)
            capacity = getattr(o, 'capacity', None)
            inventory = getattr(o, 'inventory', None)
            
            info = f"{oid:2} {name:12s} ({x:2},{y:2})"
            if inventory is not None:  # Robot
                info += f" inv:{inventory}/{capacity}"
            elif stored is not None and capacity is not None:  # Mine, Storage, Base
                info += f" mat:{stored}/{capacity}"
            
            lines.append(info)
        return '\n'.join(lines) if lines else 'No objects'
    
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
        except Exception:
            return "--:--:--"
    
    def refresh_display(loop=None, user_data=None):
        """Update all display widgets and tick robot movement."""
        # Advance robot movement each refresh (simple steady state)
        game_map.tick_movement()
        # Handle material production and consumption
        game_seconds = clock.seconds
        game_map.tick_production(game_seconds)
        map_text.set_text(build_map_display())
        object_list_text.set_text(build_object_list())
        clock_text.set_text(build_clock_display())
        if loop:
            loop.set_alarm_in(0.5, refresh_display)
    
    def process_command(cmd_line: str):
        """Process a command and return status message."""
        if not cmd_line:
            return ""
        
        try:
            parts = shlex.split(cmd_line.lower())
        except Exception:
            parts = cmd_line.lower().split()
        
        if not parts:
            return ""
        
        # Extract first word as potential command
        first = parts[0]
        
        # Quit commands
        if first in ('quit', 'exit', 'q', 'bye', 'goodbye'):
            raise urwid.ExitMainLoop()
        
        # Help
        if first in ('help', '?', 'commands'):
            return ("Natural commands:\n"
                    "• create/add TYPE at X Y - create object (e.g. 'create robot at 5 7')\n"
                    "• remove/delete at X Y or ID - remove object (e.g. 'remove at 3 4' or 'remove 5')\n"
                    "• move X Y to X Y - move object (e.g. 'move 5 7 to 10 10')\n"
                    "• robot ID go to X Y - command robot (e.g. 'robot 3 go to 8 8')\n"
                    "• what/look at X Y - inspect position (e.g. 'what at 5 7')\n"
                    "• list/objects - show all objects | show/map - display map\n"
                    "• generate terrain - create rocks | demo - add demo objects\n"
                    "• pause/resume time - control clock | reset - clear everything\n"
                    "• version - show version | help/? - this help | quit/exit - exit game")
        
        # Version
        if first in ('version', 'ver', 'v'):
            return f'KaivosAI version {VERSION}'
        
        # Time/clock commands
        if first in ('pause', 'stop') and len(parts) >= 2 and parts[1] in ('time', 'clock'):
            clock.pause()
            return 'Clock paused'
        if first == 'pause' and len(parts) == 1:
            clock.pause()
            return 'Clock paused'
        
        if first in ('resume', 'start', 'unpause'):
            if len(parts) >= 2 and parts[1] in ('time', 'clock'):
                clock.start()
                return 'Clock started'
            clock.start()
            return 'Clock started'
        
        if first == 'reset' and len(parts) >= 2 and parts[1] in ('time', 'clock'):
            clock.reset()
            return 'Clock reset'
        
        if first in ('time', 'clock'):
            if len(parts) == 1:
                return clock.show()
            sub = parts[1]
            if sub in ('show', 'display'):
                return clock.show()
            if sub in ('set', 'to') and len(parts) >= 3:
                try:
                    secs = int(parts[2])
                    clock.set_seconds(secs)
                    return f'Clock set to {secs} seconds'
                except ValueError:
                    return 'Time must be a number'
        
        # Add/create/place object
        if first in ('add', 'create', 'place', 'put', 'spawn'):
            # Patterns: "add robot at 5 7", "create mine at 3 4", "place storage 2 3"
            if len(parts) < 3:
                return 'Usage: add TYPE at X Y  or  add TYPE X Y'
            
            typ = parts[1]
            # Skip optional "at"
            if len(parts) >= 4 and parts[2] == 'at':
                try:
                    x = int(parts[3])
                    y = int(parts[4]) if len(parts) > 4 else x
                except (ValueError, IndexError):
                    return 'Coordinates must be numbers'
            else:
                try:
                    x = int(parts[2])
                    y = int(parts[3]) if len(parts) > 3 else x
                except (ValueError, IndexError):
                    return 'Coordinates must be numbers'
            
            try:
                obj = create_object(typ, None, pos=(x, y))
                game_map.add_object(obj, (x, y))
                return f'Created {typ} at ({x},{y})'
            except Exception as e:
                return f'Error: {e}'
        
        # Remove/delete object
        if first in ('remove', 'delete', 'del', 'destroy'):
            # Patterns: "remove at 5 7", "delete 3", "remove id 3"
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
            
            # Try direct: "remove 3" or "remove 5 7"
            try:
                val = int(parts[1])
                if len(parts) == 2:
                    # Single number - assume ID
                    obj = game_map.remove_object(val)
                    return f'Removed {type(obj).__name__ if obj else "nothing"}'
                else:
                    # Two numbers - assume X Y
                    y = int(parts[2])
                    obj = game_map.remove_object((val, y))
                    return f'Removed {type(obj).__name__ if obj else "nothing"}'
            except ValueError:
                return 'Invalid coordinates or ID'
        
        # Move object
        if first == 'move':
            # Patterns: "move from 1 2 to 3 4", "move 1 2 to 3 4"
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
        
        # Robot movement
        if first in ('robot', 'bot'):
            # Patterns: "robot 3 go to 5 7", "bot 3 goto 5 7"
            if len(parts) < 4:
                return 'Usage: robot ID go to X Y'
            try:
                rid = int(parts[1])
            except ValueError:
                return 'Robot ID must be a number'
            
            # Skip "go", "goto", "move"
            offset = 2
            if parts[2] in ('go', 'goto', 'move', 'walk'):
                offset = 3
            if offset < len(parts) and parts[offset] == 'to':
                offset += 1
            
            if len(parts) < offset + 2:
                return 'Usage: robot ID go to X Y'
            
            try:
                x = int(parts[offset])
                y = int(parts[offset + 1])
            except (ValueError, IndexError):
                return 'Coordinates must be numbers'
            
            try:
                started = game_map.command_move_robot(rid, (x, y))
                if started:
                    return f'Robot {rid} moving to ({x},{y})'
                else:
                    return 'No path available or already at target'
            except ValueError as e:
                return f'Error: {e}'
            except Exception as e:
                return f'Error: {e}'
        
        # Generate/create terrain
        if first in ('generate', 'gen', 'create', 'make') and len(parts) >= 2 and parts[1] in ('terrain', 'rocks', 'landscape'):
            density = 0.05
            cluster_size = 3
            # Look for numbers in remaining parts
            nums = []
            for p in parts[2:]:
                try:
                    nums.append(float(p))
                except ValueError:
                    pass
            if len(nums) >= 1:
                density = nums[0]
                if not 0.0 <= density <= 1.0:
                    return 'Density must be between 0.0 and 1.0'
            if len(nums) >= 2:
                cluster_size = int(nums[1])
                if cluster_size < 1:
                    return 'Cluster size must be at least 1'
            try:
                border, terrain = game_map.generate_full_terrain(density, cluster_size)
                return f'Terrain generated: {border} border rocks, {terrain} interior rocks'
            except Exception as e:
                return f'Error: {e}'
        
        # Show/display map
        if first in ('show', 'display', 'map', 'view'):
            return 'See Map panel'
        
        # List objects
        if first in ('list', 'objects', 'things', 'items'):
            return 'See Objects panel'
        
        # Get/inspect object at position
        if first in ('get', 'what', 'inspect', 'check', 'look') and len(parts) >= 2:
            # Patterns: "what at 5 7", "look at 5 7", "check 5 7"
            offset = 1
            if parts[1] in ('at', 'is'):
                offset = 2
            if len(parts) < offset + 2:
                return 'Usage: what at X Y'
            try:
                x = int(parts[offset])
                y = int(parts[offset + 1])
            except (ValueError, IndexError):
                return 'Coordinates must be numbers'
            obj = game_map.get((x, y))
            if obj:
                name = getattr(obj, 'name', type(obj).__name__)
                return f'{name} at ({x},{y})'
            return f'Nothing at ({x},{y})'
        
        # Reset everything
        if first == 'reset' and (len(parts) == 1 or parts[1] in ('everything', 'all', 'game', 'map')):
            for pos in list(game_map.cells.keys()):
                game_map.remove_object(pos)
            if game_map.conn:
                try:
                    game_map.conn.execute("DELETE FROM sqlite_sequence WHERE name='game_objects'")
                    game_map.conn.commit()
                except Exception:
                    pass
            clock.reset()
            return 'Everything reset: map cleared, clock reset'
        
        # Demo objects
        if first in ('demo', 'example', 'sample'):
            # Use strong randomization for demo object placement
            seed_value = int(time.time() * 1000000) + int.from_bytes(os.urandom(4), 'big')
            random.seed(seed_value)
            
            # Find free positions within 30x30 area
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
                except Exception:
                    pass
            return f'Added {added} demo objects at random positions'
        
        return f"I don't understand '{cmd_line}'. Type 'help' for commands."
    
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
    
    loop = urwid.MainLoop(main_pile, palette=palette, unhandled_input=handle_input)
    refresh_display(loop)
    loop.run()


def run_demo():
    """Start the demo with Urwid TUI."""
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