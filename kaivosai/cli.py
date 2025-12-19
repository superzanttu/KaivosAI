"""CLI and Urwid TUI for KaivosAI."""
from typing import Tuple, List
import shlex

from .db import get_game_conn, init_game_db
from .map import Map
from .models import Robot, Mine, Storage, Base, Rock, create_object
from .clock import GameClock

Position = Tuple[int, int]

# Try to import Urwid; if unavailable, fall back to old REPL
try:
    import urwid  # type: ignore
    URWID_AVAILABLE = True
except ImportError:
    URWID_AVAILABLE = False


def run_urwid_tui(game_map: Map, clock: GameClock, conn):
    """Run the Urwid-based TUI with map, object list, clock and command input."""
    
    # Widgets
    map_text = urwid.Text('', align='left')
    object_list_text = urwid.Text('', align='left')
    clock_text = urwid.Text('', align='left')
    status_text = urwid.Text('', align='left')
    command_input = urwid.Edit('> ')
    
    # Layout: map on left, object list + clock on right, status + input at bottom
    map_box = urwid.LineBox(urwid.Filler(map_text, valign='top'), title='Map')
    info_pile = urwid.Pile([
        urwid.LineBox(clock_text, title='Clock'),
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
        """Build ASCII map text."""
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
        if w > 80 or h > 40:
            return f"Region too large ({w}x{h})"
        
        grid = [["." for _ in range(w)] for __ in range(h)]
        for y in range(miny, maxy + 1):
            for x in range(minx, maxx + 1):
                obj = game_map.get((x, y))
                ch = '.'
                if obj is None:
                    ch = '.'
                elif isinstance(obj, Robot):
                    ch = 'R'
                elif isinstance(obj, Mine):
                    ch = 'M'
                elif isinstance(obj, Storage):
                    ch = 'S'
                elif isinstance(obj, Base):
                    ch = 'B'
                elif isinstance(obj, Rock):
                    ch = '#'
                else:
                    ch = '?'
                grid[y - miny][x - minx] = ch
        
        col_labels = ' '.join(str(x % 10) for x in range(minx, maxx + 1))
        lines: List[str] = ['   ' + col_labels]
        for yi, row in enumerate(grid, start=miny):
            lines.append(f"{yi:2d} " + ' '.join(row))
        lines.append("")
        lines.append("Legend: R=Robot M=Mine S=Storage B=Base #=Rock")
        return '\n'.join(lines)
    
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
            lines.append(f"{oid:2} {name:12s} ({x:2},{y:2})")
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
            parts = shlex.split(cmd_line)
        except Exception:
            parts = cmd_line.split()
        
        if not parts:
            return ""
        
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd in ('quit', 'exit', 'q'):
            raise urwid.ExitMainLoop()
        
        if cmd == 'help':
            return ("add TYPE [ID] X Y | remove X Y|ID | move X1 Y1 X2 Y2 | "
                    "get X Y | goto ROBOT_ID X Y | list | show | "
                    "time show|pause|resume|reset|set <s> | demo | terrain [density] [size] | reset | quit")
        
        if cmd == 'time':
            if not args:
                return 'Usage: time show|pause|resume|reset|set <seconds>'
            sub = args[0].lower()
            if sub == 'show':
                return clock.show()
            if sub == 'pause':
                clock.pause()
                return 'Clock paused'
            if sub in ('resume', 'start'):
                clock.start()
                return 'Clock started'
            if sub == 'reset':
                clock.reset()
                return 'Clock reset'
            if sub == 'set':
                if len(args) < 2:
                    return 'Usage: time set <seconds>'
                try:
                    secs = int(args[1])
                    clock.set_seconds(secs)
                    return 'Clock set'
                except ValueError:
                    return 'Seconds must be integer'
            return 'Unknown time command'
        
        if cmd == 'add':
            if len(args) < 3:
                return 'Usage: add TYPE [ID] X Y'
            typ = args[0]
            try:
                if len(args) == 3:
                    oid = None
                    x = int(args[1]); y = int(args[2])
                else:
                    oid = int(args[1])
                    x = int(args[2]); y = int(args[3])
            except ValueError:
                return 'ID,X,Y must be integers'
            try:
                obj = create_object(typ, oid, pos=(x, y))
                game_map.add_object(obj, (x, y))
                return f'Added {typ} at ({x},{y}) id={getattr(obj, "id", None)}'
            except Exception as e:
                return f'Error: {e}'
        
        if cmd == 'remove':
            if len(args) == 0:
                return 'Usage: remove ID  OR  remove X Y'
            if len(args) == 1:
                try:
                    oid = int(args[0])
                except ValueError:
                    return 'ID must be an integer'
                obj = game_map.remove_object(oid)
                return f'Removed: {type(obj).__name__ if obj else "None"}'
            try:
                x = int(args[0]); y = int(args[1])
            except ValueError:
                return 'X,Y must be integers'
            obj = game_map.remove_object((x, y))
            return f'Removed: {type(obj).__name__ if obj else "None"}'
        
        if cmd == 'move':
            if len(args) < 4:
                return 'Usage: move X1 Y1 X2 Y2'
            try:
                x1 = int(args[0]); y1 = int(args[1])
                x2 = int(args[2]); y2 = int(args[3])
            except ValueError:
                return 'Coordinates must be integers'
            try:
                game_map.move_object((x1, y1), (x2, y2))
                return 'Moved'
            except Exception as e:
                return f'Error: {e}'
        
        if cmd == 'list':
            # This is handled by the object list widget
            return 'See Objects panel'
        
        if cmd == 'get':
            if len(args) < 2:
                return 'Usage: get X Y'
            try:
                x = int(args[0]); y = int(args[1])
            except ValueError:
                return 'X,Y must be integers'
            obj = game_map.get((x, y))
            return str(obj) if obj else 'Empty'
        
        if cmd == 'show':
            # Map is always shown
            return 'See Map panel'
        
        if cmd == 'goto':
            if len(args) < 3:
                return 'Usage: goto ROBOT_ID X Y'
            try:
                rid = int(args[0]); x = int(args[1]); y = int(args[2])
            except ValueError:
                return 'ROBOT_ID,X,Y must be integers'
            # Debug: list available robots
            robots = [(getattr(o, 'id', None), p) for p, o in game_map.cells.items() if isinstance(o, Robot)]
            if not robots:
                return 'No robots available'
            available_ids = [rid_val for rid_val, _ in robots]
            try:
                started = game_map.command_move_robot(rid, (x, y))
                if started:
                    return f'Robot {rid} moving to ({x},{y})'
                else:
                    return 'No path available or already at target'
            except ValueError as e:
                if 'Robot id not found' in str(e):
                    return f'Robot {rid} not found. Available: {available_ids}'
                return f'Error: {e}'
            except Exception as e:
                return f'Error: {e}'
        
        if cmd == 'terrain':
            # terrain [density] [cluster_size]
            density = 0.05
            cluster_size = 3
            if len(args) >= 1:
                try:
                    density = float(args[0])
                    if not 0.0 <= density <= 1.0:
                        return 'Density must be between 0.0 and 1.0'
                except ValueError:
                    return 'Density must be a number'
            if len(args) >= 2:
                try:
                    cluster_size = int(args[1])
                    if cluster_size < 1:
                        return 'Cluster size must be >= 1'
                except ValueError:
                    return 'Cluster size must be an integer'
            try:
                border, terrain = game_map.generate_full_terrain(density, cluster_size)
                return f'Terrain generated: {border} border rocks, {terrain} terrain rocks'
            except Exception as e:
                return f'Error: {e}'
        
        if cmd == 'reset':
            # Clear all objects from map and DB
            for pos in list(game_map.cells.keys()):
                game_map.remove_object(pos)
            # Reset AUTOINCREMENT counter for fresh IDs starting from 1 (or 0 if explicitly set)
            if game_map.conn:
                try:
                    game_map.conn.execute("DELETE FROM sqlite_sequence WHERE name='game_objects'")
                    game_map.conn.commit()
                except Exception:
                    pass
            clock.reset()
            return 'Game reset: all objects removed, clock reset, ID counter reset'
        
        if cmd == 'demo':
            # Add demo objects with IDs starting from 0
            demo_objects = [
                ('mine', 0, 'Iron Mine', (0, 0), {'durability': 25}),
                ('storage', 1, 'Storage A', (1, 0), {'capacity': 50}),
                ('base', 2, 'Base', (2, 0), {}),
                ('robot', 3, 'Bot', (0, 1), {'capacity': 5}),
                ('rock', 4, 'Boulder', (1, 1), {}),
            ]
            added = 0
            for typ, oid, name, pos, kwargs in demo_objects:
                try:
                    obj = create_object(typ, oid, name=name, pos=pos, **kwargs)
                    # Remove any existing object at position
                    game_map.remove_object(pos)
                    game_map.add_object(obj, pos)
                    added += 1
                except Exception as e:
                    pass
            return f'Added {added} demo objects'
        
        return f'Unknown command: {cmd}. Type help.'
    
    def handle_input(key):
        """Handle keyboard input."""
        if key == 'enter':
            cmd_line = command_input.get_edit_text()
            command_input.set_edit_text('')
            try:
                msg = process_command(cmd_line)
                status_text.set_text(msg)
                refresh_display()  # Refresh immediately after command
            except urwid.ExitMainLoop:
                raise
            except Exception as e:
                status_text.set_text(f'Error: {e}')
        elif key in ('esc',):
            raise urwid.ExitMainLoop()
    
    loop = urwid.MainLoop(main_pile, unhandled_input=handle_input)
    refresh_display(loop)
    loop.run()


def repl(game_map: Map):
    """Old fallback REPL (when Urwid not available)."""
    import shlex

    def show_help():
        print("Commands:")
        print("  add TYPE [ID] X Y              add object (ID auto-assigned if omitted)")
        print("  remove X Y | remove ID         remove object at position or by ID")
        print("  move X1 Y1 X2 Y2               move object between positions")
        print("  get X Y                        show object at position")
        print("  goto ROBOT_ID X Y              command robot to move to target")
        print("  list                           list all objects")
        print("  show [minx maxx miny maxy]     display ASCII map (auto-bounds if omitted)")
        print("  time show|pause|resume|reset   control game clock")
        print("  time set <seconds>             set clock to specific time")
        print("  terrain [density] [size]       generate terrain (default: 0.05, 3)")
        print("  demo                           add demo objects (mine, storage, base, robot, rock)")
        print("  reset                          clear all objects and reset clock")
        print("  help                           show this help")
        print("  quit                           exit")

    def ascii_map(minx, maxx, miny, maxy):
        w = maxx - minx + 1
        h = maxy - miny + 1
        if w > 80 or h > 40:
            print(f"Region too large ({w}x{h}); limit to 80x40")
            return
        # build grid
        grid = [["." for _ in range(w)] for __ in range(h)]
        for y in range(miny, maxy + 1):
            for x in range(minx, maxx + 1):
                obj = game_map.get((x, y))
                ch = '.'
                if obj is None:
                    ch = '.'
                elif isinstance(obj, Robot):
                    ch = 'R'
                elif isinstance(obj, Mine):
                    ch = 'M'
                elif isinstance(obj, Storage):
                    ch = 'S'
                elif isinstance(obj, Base):
                    ch = 'B'
                elif isinstance(obj, Rock):
                    ch = '#'
                else:
                    ch = '?'
                grid[y - miny][x - minx] = ch

        # print x-axis header (mod 10) and rows with y coordinate labels
        col_labels = ' '.join(str(x % 10) for x in range(minx, maxx + 1))
        print('   ' + col_labels)
        for yi, row in enumerate(grid, start=miny):
            print(f"{yi:2d} " + ' '.join(row))

    import sys
    import time

    try:
        from prompt_toolkit.shortcuts import prompt
    except Exception:
        prompt = None

    spinner_chars = '|\\/-'

    while True:
        try:
            clock = getattr(game_map, 'clock', None)
            if prompt:
                def message():
                    try:
                        sec = clock.seconds if clock else int(time.time())
                    except Exception:
                        sec = int(time.time())
                    # build hh:mm:ss from seconds (wrap at 24h)
                    hh = (sec % 86400) // 3600
                    mm = (sec % 3600) // 60
                    ss = sec % 60
                    # blinking colons: visible on even seconds
                    colon = ':' if (ss % 2) == 0 else ' '
                    return f"{hh:02d}{colon}{mm:02d}{colon}{ss:02d}> "

                # refresh_interval causes the prompt UI to re-render periodically
                line = prompt(message, refresh_interval=0.2)
            else:
                # fallback: show the current time (once) in hh:mm:ss with blinking colons
                try:
                    sec = clock.seconds if clock else int(time.time())
                except Exception:
                    sec = int(time.time())
                hh = (sec % 86400) // 3600
                mm = (sec % 3600) // 60
                ss = sec % 60
                colon = ':' if (ss % 2) == 0 else ' '
                prompt_str = f"{hh:02d}{colon}{mm:02d}{colon}{ss:02d}> "
                line = input(prompt_str)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = []
        try:
            parts = shlex.split(line)
        except Exception:
            parts = line.split()
        if not parts:
            continue
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd in ('quit', 'exit'):
            break
        if cmd == 'help':
            show_help()
            continue
        if cmd == 'time':
            # time show | pause | resume | reset | set SECONDS
            if not args:
                print('Usage: time show|pause|resume|reset|set <seconds>')
                continue
            sub = args[0].lower()
            clock = getattr(game_map, 'clock', None)
            if clock is None and game_map.conn:
                clock = GameClock(game_map.conn)
                game_map.clock = clock
            if sub == 'show':
                if not clock:
                    print('No clock available')
                else:
                    print(clock.show())
                continue
            if sub == 'pause':
                if clock:
                    clock.pause()
                    print('Clock paused')
                continue
            if sub in ('resume', 'start'):
                if clock:
                    clock.start()
                    print('Clock started')
                continue
            if sub == 'reset':
                if clock:
                    clock.reset()
                    print('Clock reset')
                continue
            if sub == 'set':
                if len(args) < 2:
                    print('Usage: time set <seconds>')
                    continue
                try:
                    secs = int(args[1])
                except ValueError:
                    print('Seconds must be integer')
                    continue
                if clock:
                    clock.set_seconds(secs)
                    print('Clock set')
                continue
        if cmd == 'add':
            if len(args) < 3:
                print('Usage: add TYPE [ID] X Y')
                continue
            typ = args[0]
            try:
                if len(args) == 3:
                    oid = None
                    x = int(args[1]); y = int(args[2])
                else:
                    oid = int(args[1])
                    x = int(args[2]); y = int(args[3])
            except ValueError:
                print('ID,X,Y must be integers')
                continue
            try:
                obj = create_object(typ, oid, pos=(x, y))
                game_map.add_object(obj, (x, y))
                print('Added', typ, 'at', (x, y), 'id=', getattr(obj, 'id', None))
            except Exception as e:
                print('Error:', e)
            continue
        if cmd == 'remove':
            # Support: remove ID  OR  remove X Y
            if len(args) == 0:
                print('Usage: remove ID  OR  remove X Y')
                continue
            if len(args) == 1:
                # try ID
                try:
                    oid = int(args[0])
                except ValueError:
                    print('ID must be an integer')
                    continue
                obj = game_map.remove_object(oid)
                print('Removed:', type(obj).__name__ if obj else 'None')
                continue
            # else two args -> X Y
            try:
                x = int(args[0]); y = int(args[1])
            except ValueError:
                print('X,Y must be integers')
                continue
            obj = game_map.remove_object((x, y))
            print('Removed:', type(obj).__name__ if obj else 'None')
            continue
        if cmd == 'move':
            if len(args) < 4:
                print('Usage: move X1 Y1 X2 Y2')
                continue
            try:
                x1 = int(args[0]); y1 = int(args[1]); x2 = int(args[2]); y2 = int(args[3])
            except ValueError:
                print('Coordinates must be integers')
                continue
            try:
                game_map.move_object((x1, y1), (x2, y2))
                print('Moved')
            except Exception as e:
                print('Error:', e)
            continue
        if cmd == 'list':
            # Print header
            print('ID NAME X Y')
            for p, o in sorted(game_map.cells.items(), key=lambda kv: (getattr(kv[1], 'id', 0) or 0)):
                # Skip rocks in object list
                if isinstance(o, Rock):
                    continue
                oid = getattr(o, 'id', None)
                name = getattr(o, 'name', None) or type(o).__name__
                x, y = p
                print(f"{oid} {name} {x} {y}")
            continue
        if cmd == 'get':
            if len(args) < 2:
                print('Usage: get X Y')
                continue
            try:
                x = int(args[0]); y = int(args[1])
            except ValueError:
                print('X,Y must be integers')
                continue
            obj = game_map.get((x, y))
            print(obj if obj else 'Empty')
            continue
        if cmd == 'show':
            if len(args) == 4:
                try:
                    minx = int(args[0]); maxx = int(args[1]); miny = int(args[2]); maxy = int(args[3])
                except ValueError:
                    print('Coordinates must be integers')
                    continue
            else:
                if not game_map.cells:
                    minx = 0; miny = 0; maxx = min(game_map.width - 1, 9); maxy = min(game_map.height - 1, 9)
                else:
                    xs = [p[0] for p in game_map.cells.keys()]
                    ys = [p[1] for p in game_map.cells.keys()]
                    minx = max(0, min(xs) - 2)
                    maxx = min(game_map.width - 1, max(xs) + 2)
                    miny = max(0, min(ys) - 2)
                    maxy = min(game_map.height - 1, max(ys) + 2)
            ascii_map(minx, maxx, miny, maxy)
            continue
        if cmd == 'goto':
            # goto ROBOT_ID X Y
            if len(args) < 3:
                print('Usage: goto ROBOT_ID X Y')
                continue
            try:
                rid = int(args[0]); x = int(args[1]); y = int(args[2])
            except ValueError:
                print('ROBOT_ID,X,Y must be integers')
                continue
            # Debug: list available robots
            robots = [(getattr(o, 'id', None), p) for p, o in game_map.cells.items() if isinstance(o, Robot)]
            if not robots:
                print('No robots available')
                continue
            available_ids = [rid_val for rid_val, _ in robots]
            try:
                started = game_map.command_move_robot(rid, (x, y))
                if started:
                    print(f'Robot {rid} moving to {(x,y)}')
                else:
                    print('No path available or already at target')
            except ValueError as e:
                if 'Robot id not found' in str(e):
                    print(f'Robot {rid} not found. Available: {available_ids}')
                else:
                    print('Error:', e)
            except Exception as e:
                print('Error:', e)
            continue
        if cmd == 'reset':
            # Clear all objects from map and DB
            for pos in list(game_map.cells.keys()):
                game_map.remove_object(pos)
            # Reset AUTOINCREMENT counter for fresh IDs
            if game_map.conn:
                try:
                    game_map.conn.execute("DELETE FROM sqlite_sequence WHERE name='game_objects'")
                    game_map.conn.commit()
                except Exception:
                    pass
            clock = getattr(game_map, 'clock', None)
            if clock:
                clock.reset()
            print('Game reset: all objects removed, clock reset, ID counter reset')
            continue
        if cmd == 'demo':
            # Add demo objects with IDs starting from 0
            demo_objects = [
                ('mine', 0, 'Iron Mine', (0, 0), {'durability': 25}),
                ('storage', 1, 'Storage A', (1, 0), {'capacity': 50}),
                ('base', 2, 'Base', (2, 0), {}),
                ('robot', 3, 'Bot', (0, 1), {'capacity': 5}),
                ('rock', 4, 'Boulder', (1, 1), {}),
            ]
            added = 0
            for typ, oid, name, pos, kwargs in demo_objects:
                try:
                    obj = create_object(typ, oid, name=name, pos=pos, **kwargs)
                    # Remove any existing object at position
                    game_map.remove_object(pos)
                    game_map.add_object(obj, pos)
                    added += 1
                except Exception as e:
                    pass
            print(f'Added {added} demo objects')
            continue
        if cmd == 'terrain':
            # terrain [density] [cluster_size]
            density = 0.05
            cluster_size = 3
            if len(args) >= 1:
                try:
                    density = float(args[0])
                    if not 0.0 <= density <= 1.0:
                        print('Density must be between 0.0 and 1.0')
                        continue
                except ValueError:
                    print('Density must be a number')
                    continue
            if len(args) >= 2:
                try:
                    cluster_size = int(args[1])
                    if cluster_size < 1:
                        print('Cluster size must be >= 1')
                        continue
                except ValueError:
                    print('Cluster size must be an integer')
                    continue
            try:
                border, terrain = game_map.generate_full_terrain(density, cluster_size)
                print(f'Terrain generated: {border} border rocks, {terrain} terrain rocks')
            except Exception as e:
                print('Error:', e)
            continue
        print('Unknown command. Type help.')


def run_demo():
    """Start the demo with Urwid TUI or fallback REPL."""
    conn = get_game_conn()
    init_game_db(conn)
    game_map = Map(width=50, height=50, conn=conn)
    # Start game clock (persistent)
    clock = GameClock(conn)
    clock.start()
    
    # Only add demo objects if database is empty
    existing = list(conn.execute('SELECT COUNT(*) as cnt FROM game_objects').fetchone())
    if existing[0] == 0:
        print("Empty database detected - generating terrain and adding demo objects...")
        
        # Generate terrain first
        border, terrain = game_map.generate_full_terrain(rock_density=0.03, cluster_size=4)
        print(f"Terrain generated: {border} border rocks, {terrain} terrain rocks")
        
        # Add demo objects in safe interior positions (IDs auto-assigned to avoid conflicts)
        mine = Mine(name="Iron Mine", pos=(5, 5), durability=25)
        storage = Storage(name="Storage A", pos=(6, 5), capacity=50)
        base = Base(name="Base", pos=(7, 5))
        bot = Robot(name="Bot", pos=(5, 6), capacity=5)

        for obj in (mine, storage, base, bot):
            game_map.add_object(obj, obj.pos)
        print("Demo objects added. Use 'demo' command to recreate or 'reset' to clear.")

    if URWID_AVAILABLE:
        # Launch Urwid TUI
        try:
            run_urwid_tui(game_map, clock, conn)
        finally:
            try:
                clock.stop()
            except Exception:
                pass
            conn.close()
    else:
        # Fallback to old REPL
        print("Map initial contents:")
        for p, o in sorted(game_map.cells.items()):
            print(p, type(o).__name__, getattr(o, 'id', None))

        print("\nEntering interactive command prompt. Type 'help' for commands.")
        try:
            repl(game_map)
        finally:
            # stop clock thread if present
            try:
                clock.stop()
            except Exception:
                pass
            conn.close()
