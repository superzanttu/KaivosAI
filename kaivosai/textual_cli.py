"""Textual TUI for KaivosAI - Modern windowing system with proper layout.

Main components:
    - GameApp: Main Textual Application
    - MapDisplay: Scrollable map with coordinates and two-char cells
    - ObjectsPanel: List of objects (no rocks) with type-specific info
    - ClockDisplay: Game clock showing W<week>D<day> HH:MM:SS
    - EventsPanel: Status notifications log
    - CommandWindow: Command input and output
    
Threading:
    - Main thread: Textual event loop + UI updates
    - Background thread: GameClock (time progression, persists to DB)
"""

from typing import Tuple, List, Optional
import shlex
import random
import time
import os

from textual.app import ComposeResult, App, RenderResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Input, RichLog
from textual.screen import Screen
from textual.binding import Binding
from textual.reactive import reactive
from textual.message import Message
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from .db import get_game_conn, init_game_db, log_event
from .map import Map
from .models import Robot, Mine, Storage, Base, Rock, create_object
from .clock import GameClock
from .exceptions import CommandError, RobotError, MapError, ValidationError
from .cli import CLIController
from . import VERSION

Position = Tuple[int, int]

# Command aliases
COMMAND_ALIASES = {
    'r': 'robot', 'rob': 'robot', 'bot': 'robot',
    'm': 'mine',
    's': 'storage', 'stor': 'storage',
    'b': 'base',
    'o': 'object', 'obj': 'object',
    'c': 'create', 'add': 'create',
    'd': 'delete', 'del': 'delete', 'rem': 'delete', 'remove': 'delete',
    'g': 'goto', 'go': 'goto', 'move': 'goto',
    'l': 'load',
    'u': 'unload', 'dump': 'unload',
    'show': 'map', 'view': 'map',
    'ls': 'list', 'objects': 'list',
    't': 'terrain', 'gen': 'terrain', 'generate': 'terrain',
    'sys': 'system',
    'h': 'help', '?': 'help',
    'q': 'quit', 'exit': 'quit',
    'p': 'pause', 'stop': 'pause',
    'start': 'resume', 'unpause': 'resume',
    'v': 'version', 'ver': 'version',
    'what': 'inspect', 'look': 'inspect', 'check': 'inspect',
}


class MapDisplay(Static):
    """Scrollable map widget showing 30x30 grid with coordinates."""
    
    def __init__(self, game_map: Map, id: str = "map"):
        super().__init__(id=id)
        self.game_map = game_map
    
    def render(self) -> RenderResult:
        """Render map with X,Y coordinates and two-char cells."""
        lines = []
        
        # Header: X coordinates (0, 5, 10, 15, ...)
        header = "  Y "
        for x in range(30):
            if x % 5 == 0:
                header += f"{x:2d}"
            else:
                header += "  "
        lines.append(header)
        
        # Map rows with Y coordinate
        for y in range(30):
            row = f"{y:2d} "
            for x in range(30):
                obj = self.game_map.get((x, y))
                
                # First character: object type
                if isinstance(obj, Robot):
                    type_char = "R"
                elif isinstance(obj, Mine):
                    type_char = "M"
                elif isinstance(obj, Storage):
                    type_char = "S"
                elif isinstance(obj, Base):
                    type_char = "B"
                elif isinstance(obj, Rock):
                    type_char = "#"
                else:
                    type_char = "."
                
                # Second character: status indicator
                if isinstance(obj, Robot):
                    status_char = "▲" if obj.inventory > 0 else "○"
                elif isinstance(obj, Mine):
                    status_char = "*" if obj.stored == obj.capacity else "·"
                elif isinstance(obj, Storage):
                    status_char = "*" if obj.stored == obj.capacity else "·"
                elif isinstance(obj, Base):
                    status_char = "△" if obj.stored > 0 else "□"
                else:
                    status_char = " "
                
                row += f"{type_char}{status_char}"
            
            lines.append(row)
        
        map_text = "\n".join(lines)
        return Panel(map_text, title="MAP (30x30)", expand=False)


class ObjectsPanel(Static):
    """List of game objects (excluding rocks) with type-specific info."""
    
    def __init__(self, game_map: Map, id: str = "objects"):
        super().__init__(id=id)
        self.game_map = game_map
    
    def render(self) -> RenderResult:
        """Render objects table."""
        table = Table(title="Objects", show_header=True, expand=True)
        table.add_column("ID", style="cyan", width=4)
        table.add_column("Type", style="green", width=8)
        table.add_column("Pos", style="yellow", width=8)
        table.add_column("Data", style="white", width=20)
        
        for obj in sorted(self.game_map.cells.values(), key=lambda o: o.id):
            # Skip rocks
            if isinstance(obj, Rock):
                continue
            
            obj_type = obj.__class__.__name__
            pos_str = f"({obj.pos[0]},{obj.pos[1]})"
            
            # Type-specific data
            if isinstance(obj, Robot):
                data = f"inv:{obj.inventory}/{obj.capacity}"
            elif isinstance(obj, Mine):
                data = f"stored:{obj.stored}/{obj.capacity}"
            elif isinstance(obj, Storage):
                data = f"stored:{obj.stored}/{obj.capacity}"
            elif isinstance(obj, Base):
                data = f"stored:{obj.stored} bank:{obj.bank}"
            else:
                data = ""
            
            table.add_row(str(obj.id), obj_type, pos_str, data)
        
        return Panel(table, title="Objects", expand=True)


class ClockDisplay(Static):
    """Static clock display showing game time."""
    
    clock_text = reactive("W0 D0  00:00:00")
    
    def __init__(self, clock: Optional[GameClock] = None, id: str = "clock"):
        super().__init__(id=id)
        self.clock = clock
    
    def watch_clock_text(self) -> None:
        """Refresh when clock updates."""
        self.refresh()
    
    def render(self) -> RenderResult:
        """Render clock display."""
        return Panel(f"[bold cyan]{self.clock_text}[/bold cyan]", title="Clock", expand=False)


class EventsPanel(Static):
    """Game events log showing status changes."""
    
    def __init__(self, id: str = "events"):
        super().__init__(id=id)
        self.events: List[str] = []
    
    def add_event(self, event: str) -> None:
        """Add event to log with deduplication."""
        if not self.events or self.events[-1] != event:
            self.events.append(event)
            # Keep last 100 events
            if len(self.events) > 100:
                self.events.pop(0)
            self.refresh()
    
    def render(self) -> RenderResult:
        """Render events log."""
        events_text = "\n".join(self.events[-15:]) if self.events else "[dim]No events yet[/dim]"
        return Panel(events_text, title="Events", expand=True)


class CommandInput(Input):
    """Command input widget with enhanced styling and history support."""
    
    class CommandSubmitted(Message):
        """Posted when user submits a command."""
        def __init__(self, command: str):
            self.command = command
            super().__init__()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.command_history: List[str] = []
        self.history_index: int = -1
    
    def render(self) -> RenderResult:
        """Render input with prompt."""
        return f"[bold cyan]›[/bold cyan] {self.value}"
    
    def _on_input_submitted(self) -> None:
        """Handle Enter key."""
        command = self.value.strip()
        if command:
            if not self.command_history or self.command_history[-1] != command:
                self.command_history.append(command)
            self.history_index = -1
            self.post_message(self.CommandSubmitted(command))
            self.value = ""
    
    def action_cursor_up(self) -> None:
        """Navigate command history backwards."""
        if not self.command_history:
            return
        
        if self.history_index == -1:
            self.history_index = len(self.command_history) - 1
        elif self.history_index > 0:
            self.history_index -= 1
        
        if 0 <= self.history_index < len(self.command_history):
            self.value = self.command_history[self.history_index]
    
    def action_cursor_down(self) -> None:
        """Navigate command history forwards."""
        if not self.command_history:
            return
        
        if self.history_index != -1:
            self.history_index += 1
            if self.history_index >= len(self.command_history):
                self.history_index = -1
                self.value = ""
            else:
                self.value = self.command_history[self.history_index]


class CommandWindow(Static):
    """Command input and output window with enhanced UI."""
    
    def __init__(self, id: str = "command"):
        super().__init__(id=id)
        self.command_input: Optional[CommandInput] = None
        self.output_log: Optional[RichLog] = None
    
    def compose(self) -> ComposeResult:
        """Compose command window with help text."""
        # Header with info
        info_text = "[dim]KaivosAI Command Line[/dim] · [cyan]type 'help' for commands[/cyan]"
        yield Static(info_text, id="command-info", classes="panel-header")
        
        # Output log
        self.output_log = RichLog(markup=True, id="output-log", classes="command-output")
        yield self.output_log
        
        # Input field with border
        with Horizontal(id="input-container"):
            self.command_input = CommandInput(id="command-input")
            yield self.command_input
    
    def add_output(self, text: str, style: str = "") -> None:
        """Add output to log with optional styling."""
        if self.output_log:
            if style:
                self.output_log.write(f"[{style}]{text}[/{style}]")
            else:
                # Text may contain rich markup, write as-is
                self.output_log.write(text)
    
    def add_error(self, text: str) -> None:
        """Add error message."""
        self.add_output(text, "bold red")
    
    def add_success(self, text: str) -> None:
        """Add success message."""
        self.add_output(text, "bold green")
    
    def add_info(self, text: str) -> None:
        """Add info message."""
        self.add_output(text, "bold blue")
    
    def on_command_input_command_submitted(self, message: CommandInput.CommandSubmitted) -> None:
        """Forward command submission."""
        self.post_message(message)


class GameScreen(Screen):
    """Main game screen layout."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
    ]
    
    def __init__(self, game_map: Map, clock: Optional[GameClock] = None):
        super().__init__()
        self.game_map = game_map
        self.clock = clock
        self.conn = game_map.conn if hasattr(game_map, 'conn') else get_game_conn()
        
        # Use CLIController for command processing (avoids code duplication)
        self.cli = CLIController(game_map, clock, self.conn)
        
        # Widgets
        self.map_display: Optional[MapDisplay] = None
        self.objects_panel: Optional[ObjectsPanel] = None
        self.clock_display: Optional[ClockDisplay] = None
        self.events_panel: Optional[EventsPanel] = None
        self.command_window: Optional[CommandWindow] = None
    
    def compose(self) -> ComposeResult:
        """Compose main game screen."""
        yield Header()
        
        with Horizontal():
            # Left: Map (2/3 width)
            with Vertical(id="left-pane"):
                self.map_display = MapDisplay(self.game_map, id="map")
                yield self.map_display
            
            # Right: Clock, Objects, Events (1/3 width)
            with ScrollableContainer(id="right-pane"):
                with Vertical():
                    self.clock_display = ClockDisplay(self.clock, id="clock")
                    yield self.clock_display
                    
                    self.objects_panel = ObjectsPanel(self.game_map, id="objects")
                    yield self.objects_panel
                    
                    self.events_panel = EventsPanel(id="events")
                    yield self.events_panel
        
        # Bottom: Command window
        self.command_window = CommandWindow(id="command")
        yield self.command_window
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Setup periodic refresh and clock updates."""
        # Periodic refresh: update map, objects every 0.5s
        self.set_interval(0.5, self._refresh_displays)
        
        # Clock update: update clock display every 1s
        if self.clock:
            self.set_interval(1.0, self._update_clock)
    
    def _refresh_displays(self) -> None:
        """Refresh map and objects displays."""
        if self.map_display:
            self.map_display.refresh()
        if self.objects_panel:
            self.objects_panel.refresh()
    
    def _update_clock(self) -> None:
        """Update clock display from game clock."""
        if self.clock and self.clock_display:
            game_seconds = self.clock.seconds
            
            # Convert to weeks, days, hours, minutes, seconds
            seconds_per_day = 86400
            seconds_per_week = seconds_per_day * 7
            
            weeks = game_seconds // seconds_per_week
            remainder = game_seconds % seconds_per_week
            days = remainder // seconds_per_day
            remainder = remainder % seconds_per_day
            hours = remainder // 3600
            remainder = remainder % 3600
            minutes = remainder // 60
            seconds = remainder % 60
            
            self.clock_display.clock_text = f"W{weeks} D{days}  {hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def on_command_input_command_submitted(self, message: CommandInput.CommandSubmitted) -> None:
        """Process submitted command."""
        if self.command_window:
            # Show command with style
            self.command_window.add_output(f"[bold cyan]›[/bold cyan] {message.command}")
            
            # Handle quit command specially (needs to exit app)
            cmd_lower = message.command.strip().lower().split()[0] if message.command.strip() else ""
            if cmd_lower in ('quit', 'q', 'exit'):
                self.app.exit(return_code=0)
                return
            
            # Process command through CLIController
            try:
                result = self.cli.process_command(message.command)
                if result is not None:
                    # Detect message type
                    if cmd_lower == 'help':
                        # Help text - show as-is with markup
                        self.command_window.add_output(result)
                    elif "error" in result.lower() or "failed" in result.lower() or "unknown" in result.lower():
                        self.command_window.add_error(result)
                    elif "success" in result.lower() or "added" in result.lower() or "moved" in result.lower() or "created" in result.lower():
                        self.command_window.add_success(result)
                    else:
                        self.command_window.add_info(result)
                else:
                    self.command_window.add_error("Command returned no result")
            except (CommandError, RobotError, MapError, ValidationError) as e:
                self.command_window.add_error(str(e))
            except Exception as e:
                self.command_window.add_error(f"Unexpected error: {str(e)}")
    
    def action_quit(self) -> None:
        """Quit application."""
        self.app.exit(return_code=0)
    
    def action_help(self) -> None:
        """Show help."""
        if self.command_window:
            result = self.cli.process_command("help")
            if result:
                self.command_window.add_output(result + "\n")


class GameApp(App):
    """Main Textual application for KaivosAI."""
    
    TITLE = "KaivosAI - Mining Simulator"
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    #left-pane {
        width: 2fr;
        height: 1fr;
        overflow: auto;
    }
    
    #right-pane {
        width: 1fr;
        height: auto;
        overflow: auto;
    }
    
    #map {
        width: 1fr;
        height: 1fr;
        overflow: auto;
    }
    
    #clock {
        width: 1fr;
        height: auto;
    }
    
    #objects {
        width: 1fr;
        height: auto;
        overflow: auto;
    }
    
    #events {
        width: 1fr;
        height: auto;
        overflow: auto;
    }
    
    #command {
        width: 1fr;
        height: auto;
        border: solid $accent;
        background: $boost;
    }
    
    #command-info {
        width: 1fr;
        height: auto;
        border-bottom: solid $accent;
        text-align: center;
        padding: 0 1;
        background: $panel;
    }
    
    #output-log {
        width: 1fr;
        height: auto;
        border: none;
        background: $surface;
        padding: 1 2;
    }
    
    #input-container {
        width: 1fr;
        height: auto;
        background: $boost;
        border-top: solid $accent;
        padding: 1 2;
    }
    
    #command-input {
        width: 1fr;
        border: solid $primary;
        background: $surface;
    }
    
    #command-input:focus {
        border: solid $secondary;
        background: $boost;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
    ]
    
    def __init__(self, game_map: Map, clock: Optional[GameClock] = None):
        super().__init__()
        self.game_map = game_map
        self.clock = clock
    
    def on_mount(self) -> None:
        """Mount main game screen."""
        self.push_screen(GameScreen(self.game_map, self.clock))
    
    def action_quit(self) -> None:
        """Quit application."""
        self.exit(return_code=0)


def run_textual_tui(db_path: str = "databases/game.db") -> None:
    """Launch the Textual-based TUI.
    
    Args:
        db_path: Path to SQLite database file
    """
    from pathlib import Path
    
    # Initialize database
    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)
    conn = get_game_conn(db_path_obj)
    init_game_db(conn)
    
    # Create game map
    from .db import load_objects_from_db
    game_map = Map()
    game_map.conn = conn
    
    # Load existing objects from database
    rows = load_objects_from_db(conn)
    for row in rows:
        row_dict = dict(row)
        pos = (row_dict['x'], row_dict['y'])
        
        kwargs = {'id': row_dict['id'], 'pos': pos}
        
        for field in ['stored', 'capacity', 'inventory', 'carrying_capacity', 'commands_text', 'durability', 'bank']:
            if field in row_dict and row_dict[field] is not None:
                kwargs[field] = row_dict[field]
        
        obj = create_object(row_dict['type'], **kwargs)
        game_map.add_object(obj, pos)
    
    # Start game clock
    clock = GameClock(conn)
    clock.start()  # Start the background clock thread
    
    # Run Textual app
    app = GameApp(game_map, clock)
    app.run()
