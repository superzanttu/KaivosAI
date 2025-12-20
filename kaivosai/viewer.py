"""Real-time TUI viewer for KaivosAI using Urwid.

Polls the `game.db` and renders an ASCII viewport centered on objects.
"""
from typing import List

from .db import get_game_conn
from .clock import GameClock


def auto_bounds(rows):
    xs = [r['x'] for r in rows]
    ys = [r['y'] for r in rows]
    if not xs or not ys:
        return 0, 9, 0, 9
    minx = max(0, min(xs) - 2)
    maxx = max(xs) + 2
    miny = max(0, min(ys) - 2)
    maxy = max(ys) + 2
    return minx, maxx, miny, maxy


def build_grid_text(rows, minx, maxx, miny, maxy, header: str = "") -> str:
    w = maxx - minx + 1
    h = maxy - miny + 1
    if w <= 0 or h <= 0:
        return (header + "\n" if header else "") + "Empty region"
    if w > 160 or h > 80:
        return (header + "\n" if header else "") + f"Region too large ({w}x{h})"

    # Map of (x,y) -> char
    mapping = {}
    for r in rows:
        t = (r.get('type') or '?')
        ch = (t[0] if t else '?').upper()
        mapping[(r['x'], r['y'])] = ch

    # Column labels (x % 10)
    col_labels = ' '.join(str(x % 10) for x in range(minx, maxx + 1))
    lines: List[str] = []
    if header:
        lines.append(header)
    lines.append('   ' + col_labels)
    for y in range(miny, maxy + 1):
        row_chars = [mapping.get((x, y), '.') for x in range(minx, maxx + 1)]
        lines.append(f"{y:2d} " + ' '.join(row_chars))
    lines.append("")
    lines.append("Legend: R=Robot, M=Mine, S=Storage, B=Base, #=Rock")
    return '\n'.join(lines)


def run_viewer(poll_seconds: float = 0.5):
    import urwid  # type: ignore
    
    conn = get_game_conn()

    try:
        clock = GameClock(conn)
    except Exception:
        clock = None

    text = urwid.Text('', align='left')
    fill = urwid.Filler(text, valign='top')

    def refresh(loop, user_data=None):
        try:
            rows = list(conn.execute('SELECT id,name,x,y,type FROM game_objects'))
        except Exception:
            rows = []
        minx, maxx, miny, maxy = auto_bounds(rows)
        if clock:
            try:
                sec = clock.seconds
                hh = (sec % 86400) // 3600
                mm = (sec % 3600) // 60
                ss = sec % 60
                colon = ':' if (ss % 2) == 0 else ' '
                clock_str = f"{hh:02d}{colon}{mm:02d}{colon}{ss:02d}"
            except Exception:
                clock_str = "--:--:--"
        else:
            clock_str = "--:--:--"
        header = f"KaivosAI Viewer — {len(rows)} objects — {clock_str} — refresh {poll_seconds}s"
        text.set_text(build_grid_text(rows, minx, maxx, miny, maxy, header))
        loop.set_alarm_in(poll_seconds, refresh)

    def unhandled(key):
        if key in ('q', 'Q', 'esc'):
            raise urwid.ExitMainLoop()

    loop = urwid.MainLoop(fill, unhandled_input=unhandled)
    refresh(loop)
    try:
        loop.run()
    finally:
        conn.close()


if __name__ == '__main__':
    run_viewer()
