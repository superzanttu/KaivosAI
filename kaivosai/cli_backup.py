"""DEPRECATED: Legacy Urwid CLI backup removed.

This file was a backup of the old Urwid-based CLI implementation.
It is no longer used or maintained.

Current implementation:
    - cli.py: CLIController for command processing (UI-agnostic)
    - textual_cli.py: Textual-based TUI (modern framework)

The old file was safely removed as all functionality has been migrated to the new
framework while maintaining backward compatibility through CLIController.
"""

# This file should not be imported or used.
# Please use the current implementations instead.
raise ImportError(
    "This module is deprecated.\n"
    "Use 'from kaivosai.cli import CLIController' for command processing,\n"
    "or 'from kaivosai.textual_cli import run_textual_tui' for the TUI."
)


# All content below this point has been removed.
# The old REPL and Urwid TUI implementations are no longer maintained.
# See kaivosai/cli.py and kaivosai/textual_cli.py for current implementations.

    import shlex

    def show_help():
        print("Commands:")
        print("  add TYPE [ID] X Y         - add object (ID optional; omitted = auto-assigned)")
        print("  remove X Y                - remove object at position")
        print("  goto ROBOT_ID X Y         - command robot to move to X Y")
        print("  move X1 Y1 X2 Y2          - move object")
        print("  list                      - list all objects")
        print("  get X Y                   - show object at position")
        print("  show [minx maxx miny maxy]- show ASCII map (auto-bounds if omitted)")
        print("  time show|pause|resume|reset|set <seconds> - control game clock")
        print("  help                      - show this help")
        print("  quit                      - exit")

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
            try:
                started = game_map.command_move_robot(rid, (x, y))
                if started:
                    print(f'Robot {rid} moving to {(x,y)}')
                else:
                    print('No path available or already at target')
            except Exception as e:
                print('Error:', e)
            continue
        print('Unknown command. Type help.')


def run_demo():
    conn = get_game_conn()
    init_game_db(conn)
    game_map = Map(width=50, height=50, conn=conn)
    # start game clock (persistent)
    clock = GameClock(conn)
    game_map.clock = clock
    game_map.set_clock(clock)
    clock.start()
    mine = Mine(id=1, name="Iron Mine", pos=(0, 0), durability=25)
    storage = Storage(id=2, name="Storage A", pos=(1, 0), capacity=50)
    base = Base(id=3, name="Base", pos=(2, 0))
    bot = Robot(id=1, pos=(0, 1), capacity=5)
    rock = Rock(id=99, name="Boulder", pos=(1, 1))

    for obj in (mine, storage, base, rock, bot):
        removed = game_map.remove_object(obj.pos)
        if removed:
            print(f"Removed existing {type(removed).__name__} at {obj.pos}")
        game_map.add_object(obj, obj.pos)

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
