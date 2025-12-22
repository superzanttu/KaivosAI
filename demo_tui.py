"""Self-contained Textual demo TUI (no KaivosAI dependencies).

=== LAYOUT STRUCTURE ===
The TUI uses a hierarchical Textual container structure with CSS sizing:

    Top pane (80%)           Bottom pane (20%)
    +---------------------+---------------+
    |                     |               |
    |  Map (70%)          | Objects (30%) |
    |                     +---------------+
    |                     | Events (30%)  |
    |                     |               |
    +---------------------+---------------+
    +-------------------------------------+
    |   Commands (100% width, 20%)        |
    |   [Output log]                      |
    |   [Input field with history]        |
    +-------------------------------------+

=== WINDOWS ===
- Map: 30x30 grid with 3-character cells (type + 2-digit ID), colored
- Objects: Scrollable table (ID/Type/Pos/State), excludes rocks
- Events: Scrollable log with timestamped entries, newest at bottom
- Commands: Input field (with up/down history) + output log (scrollable)

=== CONTAINER NESTING ===
Screen (Textual root)
├─ Header
├─ Vertical #top (80% height)
│  └─ Horizontal (layout: horizontal for left/right split)
│     ├─ Vertical #left (70% width)
│     │  └─ MapWindow
│     └─ Vertical #right (30% width, stacked vertically)
│        ├─ ObjectsWindow
│        └─ EventsWindow
├─ Vertical #bottom (20% height)
│  └─ CommandsWindow
└─ Footer

=== CSS SIZING (DemoApp.CSS) ===
- height: 80% and height: 20% distribute vertical space between top/bottom
- width: 70% and width: 30% split the top pane horizontally
- height: 1fr (flex-grow) makes Objects and Events share the right pane equally
- All pane IDs (#top, #bottom, #left, #right) control their own sizes

Run with:
    python demo_tui.py
"""
from typing import Optional, List, Tuple

from textual.app import App, ComposeResult, RenderResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Input, RichLog, Static
from textual.message import Message
from textual.binding import Binding

from rich.panel import Panel
from rich.table import Table

# Demo version (separate from KaivosAI VERSION)
DEMO_VERSION = "0.1.0"

# ----------------------
# Minimal in-memory game
# ----------------------

from typing import Tuple as _Tuple

Position = _Tuple[int, int]


class BaseObject:
    def __init__(self, id: int, pos: Position, name: str = ""):
        self.id = id
        self.pos = pos
        self.name = name or self.__class__.__name__


class Robot(BaseObject):
    def __init__(self, id: int, pos: Position):
        super().__init__(id, pos)
        self.capacity = 5
        self.inventory = 0


class Mine(BaseObject):
    def __init__(self, id: int, pos: Position):
        super().__init__(id, pos)
        self.capacity = 10
        self.stored = 0


class Storage(BaseObject):
    def __init__(self, id: int, pos: Position):
        super().__init__(id, pos)
        self.capacity = 20
        self.stored = 0


class Base(BaseObject):
    def __init__(self, id: int, pos: Position):
        super().__init__(id, pos)
        self.stored = 0
        self.bank = 0


class Rock(BaseObject):
    def __init__(self, id: int, pos: Position):
        super().__init__(id, pos)


class DemoMap:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.cells: dict[Position, BaseObject] = {}
        self._next_id = 1

    def in_bounds(self, pos: Position) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, pos: Position):
        return self.cells.get(pos)

    def find_free_cell(self) -> Optional[Position]:
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) not in self.cells:
                    return (x, y)
        return None

    def _next(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def create(self, typ: str, pos: Position):
        if not self.in_bounds(pos):
            raise ValueError("Position out of bounds")
        if pos in self.cells:
            raise ValueError("Cell occupied")
        i = self._next()
        obj = None
        if typ == "robot":
            obj = Robot(i, pos)
        elif typ == "mine":
            obj = Mine(i, pos)
        elif typ == "storage":
            obj = Storage(i, pos)
        elif typ == "base":
            obj = Base(i, pos)
        elif typ == "rock":
            obj = Rock(i, pos)
        else:
            return None
        self.cells[pos] = obj
        return obj

    def remove(self, pos: Position):
        return self.cells.pop(pos, None)

    def move(self, a: Position, b: Position) -> None:
        if a not in self.cells:
            raise ValueError("Source empty")
        if not self.in_bounds(b):
            raise ValueError("Destination out of bounds")
        if b in self.cells:
            raise ValueError("Destination occupied")
        obj = self.cells.pop(a)
        obj.pos = b
        self.cells[b] = obj

    def generate_rocks(self, density: float = 0.05) -> int:
        import random
        added = 0
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) in self.cells:
                    continue
                if random.random() < max(0.0, min(1.0, density)):
                    self.create("rock", (x, y))
                    added += 1
        return added


def format_game_time(seconds: int) -> str:
    days = seconds // 86400
    rem = seconds % 86400
    hh = rem // 3600
    mm = (rem % 3600) // 60
    ss = rem % 60
    week = days // 7 + 1
    day = (days % 7) + 1
    return f"W{week}D{day} {hh:02d}:{mm:02d}:{ss:02d}"


class CommandSubmitted(Message):
    """Posted when a command is submitted."""

    def __init__(self, command: str) -> None:
        self.command = command
        super().__init__()


class CommandInput(Input):
    """Input field that posts CommandSubmitted when Enter is pressed, with history."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._history: List[str] = []
        self._hist_idx: int = -1

    def _on_input_submitted(self) -> None:  # type: ignore[override]
        text = self.value.strip()
        if text:
            if not self._history or self._history[-1] != text:
                self._history.append(text)
            self._hist_idx = -1
            self.post_message(CommandSubmitted(text))
            self.value = ""

    def action_cursor_up(self) -> None:  # history back
        if not self._history:
            return
        if self._hist_idx == -1:
            self._hist_idx = len(self._history) - 1
        elif self._hist_idx > 0:
            self._hist_idx -= 1
        if 0 <= self._hist_idx < len(self._history):
            self.value = self._history[self._hist_idx]

    def action_cursor_down(self) -> None:  # history forward
        if not self._history:
            return
        if self._hist_idx != -1:
            self._hist_idx += 1
            if self._hist_idx >= len(self._history):
                self._hist_idx = -1
                self.value = ""
            else:
                self.value = self._history[self._hist_idx]


class MapWindow(Static):
    """Map window: renders 30x30 grid with 3-character cells.
    
    Each cell displays: type character + 2-digit object ID.
    - Type chars: R(obot), M(ine), S(torage), B(ase), #(Rock), .(empty)
    - Colors: cyan(robot), yellow(mine), green(storage), magenta(base), grey(rock/empty)
    - Auto-scrollable if map exceeds container size
    
    Fills the left 70% of the top pane. Refreshed every 0.5 seconds.
    """

    def __init__(self, game_map: "DemoMap", id: str = "map") -> None:
        super().__init__(id=id)
        self.game_map = game_map

    def render(self) -> RenderResult:
        lines: List[str] = []
        for y in range(self.game_map.height):
            row = []
            for x in range(self.game_map.width):
                obj = self.game_map.get((x, y))
                if isinstance(obj, Robot):
                    tchar, color = "R", "cyan"
                    id_part = f"{obj.id % 100:02d}" if getattr(obj, "id", None) else "  "
                elif isinstance(obj, Mine):
                    tchar, color = "M", "yellow"
                    id_part = f"{obj.id % 100:02d}" if getattr(obj, "id", None) else "  "
                elif isinstance(obj, Storage):
                    tchar, color = "S", "green"
                    id_part = f"{obj.id % 100:02d}" if getattr(obj, "id", None) else "  "
                elif isinstance(obj, Base):
                    tchar, color = "B", "magenta"
                    id_part = f"{obj.id % 100:02d}" if getattr(obj, "id", None) else "  "
                elif isinstance(obj, Rock):
                    tchar, color = "#", "grey50"
                    id_part = "##"
                else:
                    tchar, color, id_part = ".", "grey30", "  "
                cell = f"[{color}]{tchar}{id_part}[/{color}]"
                row.append(cell)
            lines.append("".join(row))
        content = "\n".join(lines)
        return Panel(content, title="Map", expand=True)


class ObjectsWindow(Static):
    """Objects list: table of all non-rock objects with type-specific state.
    
    Columns: ID (cyan), Type (green), Position (yellow), State info (white)
    - Robot: inventory/capacity
    - Mine/Storage: stored/capacity
    - Base: stored amount and bank amount
    Rocks excluded from list. Scrollable, fits top-right 30% pane above Events.
    """

    def __init__(self, game_map: "DemoMap", id: str = "objects") -> None:
        super().__init__(id=id)
        self.game_map = game_map

    def render(self) -> RenderResult:
        table = Table(show_header=True, title="Objects", expand=True)
        table.add_column("ID", style="cyan", width=4)
        table.add_column("Type", style="green", width=8)
        table.add_column("Pos", style="yellow", width=8)
        table.add_column("Info", style="white")

        for obj in sorted(self.game_map.cells.values(), key=lambda o: getattr(o, "id", 0)):
            if isinstance(obj, Rock):
                continue
            obj_type = obj.__class__.__name__
            pos = getattr(obj, "pos", (0, 0))
            pos_str = f"({pos[0]},{pos[1]})"
            if isinstance(obj, Robot):
                info = f"inv:{obj.inventory}/{obj.capacity}"
            elif isinstance(obj, (Mine, Storage)):
                info = f"stored:{obj.stored}/{obj.capacity}"
            elif isinstance(obj, Base):
                info = f"stored:{obj.stored} bank:{obj.bank}"
            else:
                info = ""
            table.add_row(str(getattr(obj, "id", "?")), obj_type, pos_str, info)

        return Panel(table, title="Objects", expand=True)


class EventsWindow(Static):
    """Events log: timestamped game events, newest at bottom.
    
    Format: "W<week>D<day> HH:MM:SS <event description>"
    Shows last 20 events (scrollable). Fits bottom-right 30% pane below Objects.
    Events added via DemoApp._log() when commands change game state.
    """

    def __init__(self, events: List[str], id: str = "events") -> None:
        super().__init__(id=id)
        self._src = events

    def update_events(self) -> None:
        self.refresh()

    def render(self) -> RenderResult:
        content = "\n".join(self._src[-20:]) if self._src else "[dim]No events yet[/dim]"
        return Panel(content, title="Events", expand=True)


class CommandsWindow(Static):
    """Command input + output window: full width at bottom (20% of screen).
    
    Sections:
    - Title bar: "Demo v<version> — type 'help' for commands"
    - Output log: RichLog with command echoes and results (scrollable)
    - Input field: CommandInput with up/down arrow history navigation
    
    Commands: help, create, delete, move, list, terrain, version, quit.
    Color-coded: red errors, default success/info.
    """

    def __init__(self, id: str = "commands") -> None:
        super().__init__(id=id)
        self.output: Optional[RichLog] = None
        self.input: Optional[CommandInput] = None

    def compose(self) -> ComposeResult:
        yield Static(f"Demo v{DEMO_VERSION} — type 'help' for commands", id="cmd-title")
        self.output = RichLog(markup=True, id="cmd-output")
        yield self.output
        self.input = CommandInput(placeholder="Enter command…", id="cmd-input")
        yield self.input

    def add_line(self, text: str, style: str = "") -> None:
        if not self.output:
            return
        if style:
            self.output.write(f"[{style}]{text}[/{style}]")
        else:
            self.output.write(text)


class DemoApp(App):
    """Demo TUI with Map, Objects, Events, Commands windows."""

    CSS = """
    /* Root screen: vertical layout stacks Header, top pane, bottom pane, Footer */
    Screen { layout: vertical; }
    
    /* Top pane: 80% of vertical space (Map + Objects/Events) */
    #top { height: 80%; }
    
    /* Bottom pane: 20% of vertical space (Commands window) */
    #bottom { height: 20%; }
    
    /* Left pane in top: 70% of horizontal space (Map window) */
    #left { width: 70%; }
    
    /* Right pane in top: 30% of horizontal space (Objects + Events stacked) */
    #right { width: 30%; }
    
    /* Map fills its left pane container (1fr = flex-grow) */
    #map { height: 1fr; }
    
    /* Objects and Events share right pane equally (both 1fr) */
    #objects { height: 1fr; }
    #events { height: 1fr; }
    
    /* Commands fills bottom pane with accent border */
    #commands { height: 1fr; border: solid $accent; }
    
    /* Commands title: thin header with underline border */
    #cmd-title { padding: 0 1; border-bottom: solid $accent; }
    
    /* Commands output log: fills available space with padding */
    #cmd-output { height: 1fr; padding: 1 1; }
    
    /* Commands input: standard styled with focus highlight */
    #cmd-input { border: solid $primary; background: $surface; }
    #cmd-input:focus { border: solid $secondary; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.game_map = DemoMap(30, 30)
        self.events: List[str] = []
        self.game_seconds: int = 0
        self._last_event_seconds: int = 0  # Track last auto-event time
        self.map_win: Optional[MapWindow] = None
        self.obj_win: Optional[ObjectsWindow] = None
        self.evt_win: Optional[EventsWindow] = None
        self.cmd_win: Optional[CommandsWindow] = None

    def compose(self) -> ComposeResult:
        """Compose the TUI layout.
        
        Container structure (see module docstring for ASCII diagram):
        - Header (top bar)
        - Vertical #top (80% height):
          - Horizontal (splits left/right at 70%/30%):
            - Vertical #left (70% width): MapWindow
            - Vertical #right (30% width, stacked vertically):
              - ObjectsWindow (height: 1fr)
              - EventsWindow (height: 1fr)
        - Vertical #bottom (20% height): CommandsWindow (full width)
        - Footer (bottom bar)
        
        All sizing is controlled by CSS in DemoApp.CSS; container IDs (#top, #bottom,
        #left, #right) target specific panes. The Horizontal container inside #top
        creates the left/right split.
        """
        yield Header(show_clock=False)
        with Vertical(id="top"):  # Top pane: 80% height
            with Horizontal():  # Split left (70%) / right (30%)
                with Vertical(id="left"):  # Map pane: 70% width
                    self.map_win = MapWindow(self.game_map, id="map")
                    yield self.map_win
                with Vertical(id="right"):  # Right pane: 30% width, vertically stacked
                    self.obj_win = ObjectsWindow(self.game_map, id="objects")
                    yield self.obj_win
                    self.evt_win = EventsWindow(self.events, id="events")
                    yield self.evt_win
        with Vertical(id="bottom"):  # Bottom pane: 20% height, full width
            self.cmd_win = CommandsWindow(id="commands")
            yield self.cmd_win
        yield Footer()

    def on_mount(self) -> None:
        if self.cmd_win and self.cmd_win.output:
            self.cmd_win.output.write("Demo ready. Press q to quit.")
        # periodic refresh and clock
        self.set_interval(0.5, self._refresh_tick)
        self.set_interval(1.0, self._tick_clock)

    def _tick_clock(self) -> None:
        self.game_seconds += 1
        # Generate events every 5 seconds
        if self.game_seconds - self._last_event_seconds >= 5:
            self._generate_event()
            self._last_event_seconds = self.game_seconds

    def _refresh_tick(self) -> None:
        # refresh windows
        if self.map_win:
            self.map_win.refresh()
        if self.obj_win:
            self.obj_win.refresh()
        if self.evt_win:
            self.evt_win.update_events()

    def on_command_submitted(self, message: CommandSubmitted) -> None:
        cmd = message.command.strip()
        if not cmd:
            return
        if self.cmd_win:
            self.cmd_win.add_line(f"[cyan]›[/cyan] {cmd}")
        result = self._process_command(cmd)
        if self.cmd_win and result:
            low = result.lower()
            if any(k in low for k in ("error", "failed", "usage", "unknown")):
                self.cmd_win.add_line(result, style="red")
            else:
                self.cmd_win.add_line(result)

    def action_quit(self) -> None:
        self.exit()

    def _generate_event(self) -> None:
        """Generate a random game event every 5 seconds."""
        import random
        if not self.game_map.cells:
            return
        
        event_types = [
            "Status update",
            "Activity detected",
            "Tick completed",
            "System nominal",
            "Cycle finished",
        ]
        
        # Randomly pick an object to mention (or just report system event)
        if random.random() < 0.6 and self.game_map.cells:
            obj = random.choice(list(self.game_map.cells.values()))
            obj_type = obj.__class__.__name__
            x, y = obj.pos
            base_event = random.choice(event_types)
            self._log(f"{base_event}: {obj_type} at ({x},{y})")
        else:
            self._log(random.choice(event_types))


    # --- Simple in-memory game logic below ---

    def _log(self, text: str) -> None:
        self.events.append(f"{format_game_time(self.game_seconds)} {text}")

    def _process_command(self, cmd: str) -> str:
        parts = cmd.strip().split()
        if not parts:
            return ""
        op = parts[0].lower()
        try:
            if op in ("help", "h", "?"):
                return (
                    "Commands:\n"
                    "  help                         Show this help\n"
                    "  create <type> [x y]         Types: robot|mine|storage|base|rock\n"
                    "  delete <x> <y>               Remove object at position\n"
                    "  move <x1> <y1> <x2> <y2>     Move object from -> to\n"
                    "  list                         List objects\n"
                    "  terrain [density]            Add random rocks (0.0-1.0, default 0.05)\n"
                    "  version                      Show demo version\n"
                    "  quit                         Quit demo"
                )
            if op == "version":
                return f"Demo v{DEMO_VERSION}"
            if op == "quit":
                self.exit()
                return ""
            if op == "list":
                lines = []
                for obj in sorted(self.game_map.cells.values(), key=lambda o: getattr(o, "id", 0)):
                    if isinstance(obj, Rock):
                        continue
                    t = obj.__class__.__name__
                    x, y = obj.pos
                    if isinstance(obj, Robot):
                        info = f"inv:{obj.inventory}/{obj.capacity}"
                    elif isinstance(obj, (Mine, Storage)):
                        info = f"stored:{obj.stored}/{obj.capacity}"
                    elif isinstance(obj, Base):
                        info = f"stored:{obj.stored} bank:{obj.bank}"
                    else:
                        info = ""
                    lines.append(f"{obj.id:02d} {t} ({x},{y}) {info}")
                return "\n".join(lines) if lines else "No objects"
            if op == "create":
                if len(parts) < 2:
                    return "Usage: create <robot|mine|storage|base|rock> [x y]"
                typ = parts[1].lower()
                if len(parts) >= 4:
                    x, y = int(parts[2]), int(parts[3])
                    pos = (x, y)
                else:
                    pos = self.game_map.find_free_cell() or (0, 0)
                obj = self.game_map.create(typ, pos)
                if obj is None:
                    return f"Unknown type: {typ}"
                self._log(f"{typ.capitalize()}{obj.id} created at ({pos[0]},{pos[1]})")
                return f"Created {typ} {obj.id} at {pos}"
            if op == "delete":
                if len(parts) != 3:
                    return "Usage: delete <x> <y>"
                pos = (int(parts[1]), int(parts[2]))
                obj = self.game_map.remove(pos)
                if obj:
                    self._log(f"Deleted {obj.__class__.__name__}{obj.id} at ({pos[0]},{pos[1]})")
                    return f"Deleted {obj.__class__.__name__} {obj.id}"
                return "Nothing to delete"
            if op == "move":
                if len(parts) != 5:
                    return "Usage: move <x1> <y1> <x2> <y2>"
                a = (int(parts[1]), int(parts[2]))
                b = (int(parts[3]), int(parts[4]))
                self.game_map.move(a, b)
                self._log(f"Moved object from ({a[0]},{a[1]}) to ({b[0]},{b[1]})")
                return "Moved"
            if op == "terrain":
                density = float(parts[1]) if len(parts) >= 2 else 0.05
                added = self.game_map.generate_rocks(density)
                self._log(f"Generated {added} rocks")
                return f"Added {added} rocks"
            return f"Unknown command: {op}"
        except Exception as e:
            return f"Error: {e}"


def main() -> None:
    app = DemoApp()
    app.run()


if __name__ == "__main__":
    main()
