"""Deprecated: Legacy Urwid viewer removed.

The old Urwid-based read-only viewer (run_viewer) has been removed.
The actual TUI is now provided by textual_cli.py using the Textual framework.

For monitoring and viewing the game state, use:
    python -m kaivosai  # Launches the Textual-based TUI

Utility functions build_grid_text() and auto_bounds() remain for reference
if you need to build simple ASCII displays, but they are not used by the main TUI.
"""

from typing import List, Tuple


def auto_bounds(rows) -> Tuple[int, int, int, int]:
    """Compute viewport bounds centered around existing objects.

    Args:
        rows: Iterable of DB rows with 'x' and 'y' coordinates

    Returns:
        Tuple `(minx, maxx, miny, maxy)` with a 2-cell margin.

    Note:
        Returns default `(0,9,0,9)` if no rows found.
    """
    xs = [r['x'] for r in rows]
    ys = [r['y'] for r in rows]
    if not xs or not ys:
        return 0, 9, 0, 9
    minx = max(0, min(xs) - 2)
    maxx = max(xs) + 2
    miny = max(0, min(ys) - 2)
    maxy = max(ys) + 2
    return minx, maxx, miny, maxy


def build_grid_text(rows, minx: int, maxx: int, miny: int, maxy: int, 
                   header: str = "") -> str:
    """Render ASCII grid display (legacy reference).

    Args:
        rows: Iterable of rows with 'x', 'y', and 'type'
        minx: Minimum x coordinate
        maxx: Maximum x coordinate
        miny: Minimum y coordinate
        maxy: Maximum y coordinate
        header: Optional header string shown above the grid

    Returns:
        Multi-line string with coordinates and legend.
    
    Note:
        Uses first letter of type as symbol: R/M/S/B/#.
        This function is kept for reference but not used in current TUI.
    """
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
    """Deprecated: Urwid viewer removed.
    
    Use the Textual-based TUI instead:
        python -m kaivosai
    
    Original purpose:
        - Read-only viewer that polled the game.db
        - Displayed objects in an ASCII grid format
        - Updated every poll_seconds (default 0.5s)
    
    This function is no longer available. Use the main TUI.
    """
    raise NotImplementedError(
        "The Urwid-based viewer has been removed.\n"
        "Use the main TUI instead: python -m kaivosai"
    )


if __name__ == '__main__':
    run_viewer()
