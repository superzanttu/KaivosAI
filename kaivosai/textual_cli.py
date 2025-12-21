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
    """Command input widget."""
    
    class CommandSubmitted(Message):
        """Posted when user submits a command."""
        def __init__(self, command: str):
            self.command = command
            super().__init__()
    
    def _on_input_submitted(self) -> None:
        """Handle Enter key."""
        command = self.value.strip()
        if command:
            self.post_message(self.CommandSubmitted(command))
            self.value = ""


class CommandWindow(Static):
    """Command input and output window."""
    
    def __init__(self, id: str = "command"):
        super().__init__(id=id)
        self.command_input: Optional[CommandInput] = None
        self.output_log: Optional[RichLog] = None
    
    def compose(self) -> ComposeResult:
        """Compose command window."""
        self.output_log = RichLog(markup=True, id="output-log")
        yield self.output_log
        self.command_input = CommandInput(id="command-input")
        yield self.command_input
    
    def add_output(self, text: str) -> None:
        """Add output to log."""
        if self.output_log:
            self.output_log.write(text)
    
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
            self.command_window.add_output(f"> {message.command}\n")
            result = self._process_command(message.command)
            if result:
                self.command_window.add_output(f"{result}\n")
    
    def _process_command(self, command_str: str) -> str:
        """Process natural language command."""
        command_str = command_str.strip()
        if not command_str:
            return "Empty command"
        
        parts = shlex.split(command_str)
        if not parts:
            return "Invalid command"
        
        # Expand aliases
        primary = parts[0].lower()
        if primary in COMMAND_ALIASES:
            parts[0] = COMMAND_ALIASES[primary]
        
        cmd = parts[0].lower()
        
        # Route to handlers
        if cmd == 'create':
            return self._handle_create(parts)
        elif cmd == 'delete':
            return self._handle_delete(parts)
        elif cmd == 'move' or cmd == 'goto':
            return self._handle_move(parts)
        elif cmd == 'load':
            return self._handle_load(parts)
        elif cmd == 'unload':
            return self._handle_unload(parts)
        elif cmd == 'robot':
            return self._handle_robot(parts)
        elif cmd == 'map':
            return self._handle_map(parts)
        elif cmd == 'list':
            return self._handle_list(parts)
        elif cmd == 'inspect':
            return self._handle_inspect(parts)
        elif cmd == 'system':
            return self._handle_system(parts)
        elif cmd == 'help':
            return self._show_help()
        elif cmd == 'quit':
            self.app.exit()
            return "Quitting..."
        else:
            return f"Unknown command: {cmd}. Type 'help' for commands."
    
    def _handle_create(self, parts: List[str]) -> str:
        """Create object: create <type> [x] [y]"""
        if len(parts) < 2:
            return "Usage: create <robot|mine|storage|base|rock> [x] [y]"
        
        obj_type = parts[1].lower()
        if obj_type not in ['robot', 'mine', 'storage', 'base', 'rock']:
            return f"Unknown object type: {obj_type}"
        
        # Get position or random
        if len(parts) >= 4:
            try:
                x, y = int(parts[2]), int(parts[3])
            except ValueError:
                return "Position must be integers"
        else:
            x, y = random.randint(0, 29), random.randint(0, 29)
        
        try:
            obj = create_object(obj_type, pos=(x, y))
            self.game_map.add_object(obj, (x, y))
            return f"Created {obj_type} at ({x}, {y})"
        except Exception as e:
            return f"Failed to create {obj_type}: {str(e)}"
    
    def _handle_delete(self, parts: List[str]) -> str:
        """Delete object: delete <id>"""
        if len(parts) < 2:
            return "Usage: delete <id>"
        
        try:
            obj_id = int(parts[1])
        except ValueError:
            return "ID must be an integer"
        
        obj = self.game_map.get_object_by_id(obj_id)
        if not obj:
            return f"No object with ID {obj_id}"
        
        try:
            self.game_map.remove_object(obj_id)
            return f"Deleted object {obj_id}"
        except Exception as e:
            return f"Failed to delete object: {str(e)}"
    
    def _handle_move(self, parts: List[str]) -> str:
        """Move robot: move <id> <x> <y>"""
        if len(parts) < 4:
            return "Usage: move <id> <x> <y>"
        
        try:
            obj_id, x, y = int(parts[1]), int(parts[2]), int(parts[3])
        except ValueError:
            return "Arguments must be integers"
        
        obj = self.game_map.get_object_by_id(obj_id)
        if not obj:
            return f"No object with ID {obj_id}"
        
        if not isinstance(obj, Robot):
            return "Only robots can move"
        
        try:
            self.game_map.move_object(obj, (x, y))
            return f"Moved robot {obj_id} to ({x}, {y})"
        except Exception as e:
            return f"Failed to move robot: {str(e)}"
    
    def _handle_load(self, parts: List[str]) -> str:
        """Load materials: load <robot_id> [amount]"""
        if len(parts) < 2:
            return "Usage: load <robot_id> [amount]"
        
        try:
            robot_id = int(parts[1])
            amount = int(parts[2]) if len(parts) > 2 else None
        except ValueError:
            return "Arguments must be integers"
        
        robot = self.game_map.get_object_by_id(robot_id)
        if not robot or not isinstance(robot, Robot):
            return f"Robot {robot_id} not found"
        
        return "Load command not yet implemented in detail"
    
    def _handle_unload(self, parts: List[str]) -> str:
        """Unload materials: unload <robot_id> [amount]"""
        if len(parts) < 2:
            return "Usage: unload <robot_id> [amount]"
        
        return "Unload command not yet implemented in detail"
    
    def _handle_robot(self, parts: List[str]) -> str:
        """Robot commands: robot <id> <subcommand>"""
        if len(parts) < 3:
            return "Usage: robot <id> <goto|load|unload|code|start|pause>"
        
        try:
            robot_id = int(parts[1])
        except ValueError:
            return "Robot ID must be integer"
        
        robot = self.game_map.get_object_by_id(robot_id)
        if not robot or not isinstance(robot, Robot):
            return f"Robot {robot_id} not found"
        
        subcmd = parts[2].lower()
        
        if subcmd == 'goto':
            if len(parts) < 5:
                return "Usage: robot <id> goto <x> <y>"
            try:
                x, y = int(parts[3]), int(parts[4])
                self.game_map.move_object(robot, (x, y))
                return f"Robot {robot_id} moving to ({x}, {y})"
            except Exception as e:
                return f"Move failed: {str(e)}"
        else:
            return f"Robot subcommand '{subcmd}' not yet implemented"
    
    def _handle_map(self, parts: List[str]) -> str:
        """Map commands: map [terrain]"""
        if len(parts) > 1 and parts[1].lower() == 'terrain':
            return "Terrain generation not yet implemented"
        return "Map displayed in main window"
    
    def _handle_list(self, parts: List[str]) -> str:
        """List objects: list"""
        count = len([o for o in self.game_map.cells.values() if not isinstance(o, Rock)])
        return f"Objects window shows {count} objects (excluding rocks)"
    
    def _handle_inspect(self, parts: List[str]) -> str:
        """Inspect object: inspect <id>"""
        if len(parts) < 2:
            return "Usage: inspect <id>"
        
        try:
            obj_id = int(parts[1])
        except ValueError:
            return "ID must be integer"
        
        obj = self.game_map.get_object_by_id(obj_id)
        if not obj:
            return f"No object with ID {obj_id}"
        
        details = f"{obj.__class__.__name__} #{obj.id} at {obj.pos}"
        if hasattr(obj, 'inventory'):
            details += f" | inventory: {obj.inventory}/{obj.capacity}"
        if hasattr(obj, 'stored'):
            details += f" | stored: {obj.stored}/{obj.capacity}"
        
        return details
    
    def _handle_system(self, parts: List[str]) -> str:
        """System commands: system <help|version|quit|pause|resume|optimize>"""
        if len(parts) < 2:
            return "Usage: system <help|version|quit|pause|resume|optimize>"
        
        subcmd = parts[1].lower()
        
        if subcmd == 'quit':
            self.app.exit()
            return "Quitting..."
        elif subcmd == 'help':
            return self._show_help()
        elif subcmd == 'version':
            return f"KaivosAI version {VERSION}"
        elif subcmd == 'pause':
            if self.clock:
                self.clock.pause()
            return "Clock paused"
        elif subcmd == 'resume':
            if self.clock:
                self.clock.start()
            return "Clock resumed"
        elif subcmd == 'optimize':
            return self._optimize_ids()
        else:
            return f"Unknown system command: {subcmd}"
    
    def _show_help(self) -> str:
        """Show help text."""
        help_text = """COMMANDS:
create <type> [x] [y]    - Create object (robot, mine, storage, base)
delete <id>              - Delete object
move <id> <x> <y>        - Move object
robot <id> goto <x> <y>  - Move robot to coordinates
list                     - List objects
inspect <id>             - Show object details
system version           - Show version
system help              - Show this help
system optimize          - Renumber IDs
system pause/resume      - Control game clock
help, ?                  - Show this help
quit, q                  - Exit game"""
        return help_text
    
    def _optimize_ids(self) -> str:
        """Renumber all object IDs sequentially."""
        if not self.game_map.cells:
            return "No objects to optimize"
        
        try:
            objects = sorted(self.game_map.cells.values(), key=lambda o: o.id)
            id_map = {}
            new_id = 1
            for obj in objects:
                id_map[obj.id] = new_id
                new_id += 1
            
            old_cells = self.game_map.cells.copy()
            self.game_map.cells = {}
            
            from .db import delete_object_db, persist_object
            
            for obj in objects:
                old_id = obj.id
                new_obj_id = id_map[old_id]
                
                if old_id != new_obj_id:
                    delete_object_db(self.conn, old_id)
                
                obj.id = new_obj_id
                self.game_map.cells[obj.pos] = obj
                persist_object(self.conn, obj)
            
            count = len(objects)
            return f"Optimized: renumbered {count} objects to 1-{count}"
        except Exception as e:
            return f"Optimization failed: {str(e)}"
    
    def action_quit(self) -> None:
        """Quit application."""
        self.app.exit()
    
    def action_help(self) -> None:
        """Show help."""
        if self.command_window:
            self.command_window.add_output(self._show_help() + "\n")


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
    }
    
    #output-log {
        width: 1fr;
        height: auto;
        border: none;
        background: $surface;
    }
    
    #command-input {
        width: 1fr;
        border-top: solid $primary;
        margin: 1 2;
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
        self.exit()


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
