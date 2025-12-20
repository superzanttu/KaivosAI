"""CLI and Urwid TUI for KaivosAI."""
from typing import Tuple, List
import shlex
import random
import time
import os

from .db import get_game_conn, init_game_db, log_event
from .map import Map
from .models import Robot, Mine, Storage, Base, Rock, create_object
from .clock import GameClock
from . import VERSION

Position = Tuple[int, int]

import urwid  # type: ignore

# Command aliases (short -> full form)
COMMAND_ALIASES = {
    # Objects
    'r': 'robot',
    'rob': 'robot',
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

# Available commands for tab completion
COMPLETIONS = [
    'robot', 'mine', 'storage', 'base', 'rock', 'object',
    'create', 'delete', 'goto', 'load', 'unload',
    'map', 'terrain', 'demo', 'reset', 'list', 'inspect',
    'system', 'help', 'quit', 'pause', 'resume', 'version',
]


class CommandEdit(urwid.Edit):
    """Edit widget with tab completion support."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.completions = COMPLETIONS
        self.completion_index = -1
        self.original_text = ""
    
    def keypress(self, size, key):
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
    """Expand command aliases to full form."""
    return [COMMAND_ALIASES.get(p, p) for p in parts]


def run_urwid_tui(game_map: Map, clock: GameClock, conn):
    """Run the Urwid-based TUI with map, object list, clock and command input."""
    
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
        """Build object list display with colors and status indicators."""
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
                
                markup.append((color, f"R {oid:2d} {name:10s}"))
                markup.append(('dim', f" @({x:2d},{y:2d}) "))
                markup.append((color, f"{bar} {inventory}/{capacity}"))
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
                
                if stored > 0:
                    color = 'base'
                    status = 'ACTIVE'
                else:
                    color = 'base_empty'
                    status = 'IDLE'
                
                markup.append((color, f"B {oid:2d} {name:10s}"))
                markup.append(('dim', f" @({x:2d},{y:2d}) "))
                markup.append((color, f"{status} mat:{stored}"))
                markup.append('\\n')
        
        return markup
    
    def build_events_display():
        """Build recent events list with color-coded event types."""
        if not conn:
            return [('dim', 'No database connection')]
        
        from .db import get_recent_events
        from .clock import GameClock
        
        try:
            events = get_recent_events(conn, limit=15)
            if not events:
                return [('dim', 'No events yet')]
            
            markup = []
            for event in events:
                timestamp, obj_id, obj_type, event_type, message, x, y = event
                # Format timestamp
                weeks, remainder = divmod(int(timestamp), 7 * 24 * 3600)
                days, remainder = divmod(remainder, 24 * 3600)
                hours, remainder = divmod(remainder, 3600)
                minutes, seconds = divmod(remainder, 60)
                time_str = f"W{weeks+1}D{days+1} {hours:02d}:{minutes:02d}"
                
                # Determine event color and ASCII symbol based on type
                if event_type in ('robot_arrived', 'robot_loaded', 'robot_unloaded', 'base_supplied'):
                    event_color = 'event_good'
                    symbol = '+'
                elif event_type in ('robot_blocked', 'robot_empty', 'mine_empty', 'storage_empty', 'base_empty'):
                    event_color = 'event_bad'
                    symbol = '!'
                elif event_type in ('robot_full', 'mine_full', 'storage_full'):
                    event_color = 'warning'
                    symbol = '*'
                else:
                    event_color = 'event_neutral'
                    symbol = '-'
                
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
                
                # Truncate message if too long
                if len(message) > 35:
                    message = message[:32] + '...'
                
                markup.append(('event_time', time_str))
                markup.append(' ')
                markup.append((event_color, symbol))
                if obj_letter:
                    markup.append((obj_color, obj_letter))
                markup.append(' ')
                markup.append((event_color, message))
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
        except Exception:
            return "--:--:--"
    
    def show_version_dialog():
        """Show modal dialog for new version notification."""
        from pathlib import Path
        from kaivosai import VERSION as NEW_VERSION
        
        # Create dialog content
        banner = urwid.Text(('version_banner', f' NEW VERSION AVAILABLE: {NEW_VERSION} '), align='center')
        message = urwid.Text('\nA new version of KaivosAI has been detected.\n', align='center')
        instructions = urwid.Text('Press any key to restart\nPress ESC to quit', align='center')
        
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
            if key == 'esc':
                # User wants to quit
                flag_file = Path(__file__).parent.parent / "flag_new_version.lck"
                try:
                    flag_file.unlink()  # Remove flag file
                except Exception:
                    pass
                raise urwid.ExitMainLoop()
            else:
                # Any other key: restart
                flag_file = Path(__file__).parent.parent / "flag_new_version.lck"
                try:
                    flag_file.unlink()  # Remove flag file
                except Exception:
                    pass
                import sys
                import os
                sys.stdout.flush()
                os.execv(sys.executable, [sys.executable] + sys.argv)
        
        loop.widget = overlay
        loop.unhandled_input = handle_version_key
    
    def refresh_display(loop=None, user_data=None):
        """Update all display widgets and tick robot movement."""
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
        map_text.set_text(build_map_display())
        object_list_text.set_text(build_object_list())
        events_text.set_text(build_events_display())
        clock_text.set_text(build_clock_display())
        if loop:
            loop.set_alarm_in(0.5, refresh_display)
    
    def process_command(cmd_line: str):
        """Process a command and return status message.
        
        Syntax: <object> [id] <verb> [params...]
        Examples:
            robot 3 goto 5 7    (r 3 g 5 7)
            robot 3 load        (r 3 l)
            robot 3 unload 5    (r 3 u 5)
            create robot 5 7    (c robot 5 7 or c r 5 7)
            delete 3            (d 3)
            delete 5 7          (d 5 7)
            list                (ls)
            map                 (m)
        """
        if not cmd_line:
            return ""
        
        try:
            parts = shlex.split(cmd_line.lower())
        except Exception:
            parts = cmd_line.lower().split()
        
        if not parts:
            return ""
        
        # Expand aliases
        parts = expand_aliases(parts)
        first = parts[0]
        
        # System commands: system <subcommand>
        if first == 'system':
            if len(parts) < 2:
                return 'Usage: system <help|version|quit|pause|resume>'
            sub = parts[1]
            
            if sub == 'quit':
                raise urwid.ExitMainLoop()
            elif sub == 'help':
                # Recursively call with help
                return process_command('help')
            elif sub == 'version':
                return f'KaivosAI version {VERSION}'
            elif sub == 'pause':
                clock.pause()
                return 'Clock paused'
            elif sub == 'resume':
                clock.start()
                return 'Clock resumed'
            else:
                return f"Unknown system command: {sub}"
        
        # Map commands: map <subcommand>
        if first == 'map':
            if len(parts) < 2:
                # Just "map" shows the map
                return 'See Map panel'
            sub = parts[1]
            
            if sub == 'show':
                return 'See Map panel'
            elif sub == 'list':
                return 'See Objects panel'
            elif sub == 'terrain':
                # map terrain [density] [size]
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
                except Exception as e:
                    return f'Error: {e}'
            elif sub == 'demo':
                # Add demo objects
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
                    except Exception:
                        pass
                return f'Added {added} demo objects at random positions'
            elif sub == 'reset':
                # Clear everything
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
            else:
                return f"Unknown map command: {sub}. Try: show, list, terrain, demo, reset"
        
        # Legacy standalone commands for backwards compatibility
        if first == 'quit':
            raise urwid.ExitMainLoop()
        
        # Help
        if first == 'help':
            return ("Commands (with shortcuts):\n"
                    "ROBOTS:\n"
                    "• robot ID goto X Y (r ID g X Y) - move robot to position\n"
                    "• robot ID load [amount] (r ID l) - load from adjacent object\n"
                    "• robot ID unload [amount] (r ID u) - unload to adjacent object\n"
                    "\n"
                    "OBJECTS:\n"
                    "• create TYPE X Y (c TYPE X Y) - create object at position\n"
                    "• delete ID (d ID) - remove object by ID\n"
                    "• delete X Y (d X Y) - remove object at position\n"
                    "• inspect X Y - inspect position\n"
                    "\n"
                    "MAP:\n"
                    "• map show (map/m) - show map\n"
                    "• map list (map ls) - show all objects\n"
                    "• map terrain [density] [size] (map t) - generate terrain\n"
                    "• map demo (map demo) - add demo objects\n"
                    "• map reset (map reset) - clear everything\n"
                    "\n"
                    "SYSTEM:\n"
                    "• system pause (sys p) - pause clock\n"
                    "• system resume (sys start) - resume clock\n"
                    "• system version (sys v) - show version\n"
                    "• system help (sys h) - this help\n"
                    "• system quit (sys q) - exit\n"
                    "\n"
                    "Press TAB for command completion")
        
        # Version (legacy standalone)
        if first == 'version':
            return f'KaivosAI version {VERSION}'
        
        # Pause/Resume (legacy standalone)
        if first == 'pause':
            clock.pause()
            return 'Clock paused'
        
        if first == 'resume':
            clock.start()
            return 'Clock resumed'
        
        # Create object: create TYPE X Y
        if first == 'create':
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
        
        # Delete object: delete ID or delete X Y
        if first == 'delete':
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
            # Patterns: "robot 3 go to 5 7", "bot 3 goto 5 7", "robot 3 load", "robot 3 unload"
            if len(parts) < 2:
                return 'Usage: robot ID <command>'
            try:
                rid = int(parts[1])
            except ValueError:
                return 'Robot ID must be a number'
            
            # Find the robot
            robot = None
            for obj in game_map.cells.values():
                if isinstance(obj, Robot) and getattr(obj, 'id', None) == rid:
                    robot = obj
                    break
            
            if not robot:
                return f'Robot {rid} not found'
            
            # Load command
            if len(parts) >= 3 and parts[2] in ('load', 'take', 'pickup', 'get'):
                adjacent = game_map.get_adjacent_objects(robot.pos)
                # Filter to valid sources: Mine, Storage, Base, Robot
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
                
                loaded = robot.load_from(source, amount)
                if loaded > 0:
                    # Persist both objects
                    if conn:
                        from .db import persist_object
                        persist_object(conn, robot)
                        persist_object(conn, source)
                        # Log event
                        game_seconds = clock.seconds if clock else 0
                        source_name = getattr(source, 'name', type(source).__name__)
                        log_event(conn, game_seconds, 'robot_loaded', 
                                 f'Robot {rid} loaded {loaded} from {source_name} at ({robot.pos[0]},{robot.pos[1]})', robot, robot.pos)
                        # Check if robot is full
                        if robot.inventory >= robot.capacity:
                            log_event(conn, game_seconds, 'robot_full', 
                                     f'Robot {rid} inventory full ({robot.inventory}/{robot.capacity})', robot, robot.pos)
                    source_name = getattr(source, 'name', type(source).__name__)
                    return f'Robot {rid} loaded {loaded} material from {source_name}. Inventory: {robot.inventory}/{robot.capacity}'
                else:
                    return f'Could not load (robot full or source empty)'
            
            # Unload command
            if len(parts) >= 3 and parts[2] in ('unload', 'dump', 'drop', 'put', 'store'):
                adjacent = game_map.get_adjacent_objects(robot.pos)
                # Filter to valid targets: Storage, Base, Robot
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
                
                unloaded = robot.unload_to(target, amount)
                if unloaded > 0:
                    # Persist both objects
                    if conn:
                        from .db import persist_object
                        persist_object(conn, robot)
                        persist_object(conn, target)
                        # Log event
                        game_seconds = clock.seconds if clock else 0
                        target_name = getattr(target, 'name', type(target).__name__)
                        log_event(conn, game_seconds, 'robot_unloaded', 
                                 f'Robot {rid} unloaded {unloaded} to {target_name} at ({robot.pos[0]},{robot.pos[1]})', robot, robot.pos)
                        # Check if robot is empty
                        if robot.inventory == 0:
                            log_event(conn, game_seconds, 'robot_empty', 
                                     f'Robot {rid} inventory empty', robot, robot.pos)
                    target_name = getattr(target, 'name', type(target).__name__)
                    return f'Robot {rid} unloaded {unloaded} material to {target_name}. Inventory: {robot.inventory}/{robot.capacity}'
                else:
                    return f'Could not unload (robot empty or target full)'
            
            # Skip "go", "goto", "move" for movement commands
            if len(parts) < 4:
                return 'Usage: robot ID <go to X Y | load [amount] | unload [amount]>'
            
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
                    # Log movement start event
                    if conn:
                        game_seconds = clock.seconds if clock else 0
                        name = getattr(robot, 'name', f'Robot {rid}')
                        log_event(conn, game_seconds, 'robot_moving', 
                                 f'{name} started moving to ({x},{y}) from ({robot.pos[0]},{robot.pos[1]})', robot, robot.pos)
                    return f'Robot {rid} moving to ({x},{y})'
                else:
                    return 'No path available or already at target'
            except ValueError as e:
                return f'Error: {e}'
            except Exception as e:
                return f'Error: {e}'
        
        # Legacy standalone commands
        # Terrain (legacy - use "map terrain" instead)
        if first == 'terrain':
            return 'Use "map terrain [density] [size]" or "map t" instead'
        
        # List objects (legacy - use "map list" instead)
        if first == 'list':
            return 'See Objects panel (or use "map list")'
        
        # Inspect position: inspect X Y
        if first == 'inspect':
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
        
        # Reset (legacy - use "map reset" instead)
        if first == 'reset':
            return 'Use "map reset" instead'
        
        # Demo (legacy - use "map demo" instead)
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