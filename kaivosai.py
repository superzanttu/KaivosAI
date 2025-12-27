"""KaivosAI - Main entry point with Textual TUI."""

import asyncio
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ListView, ListItem, DataTable

import database
from version import VERSION
import exceptions
from gameloop import GameLoop

OBJECTS = [
    ("ID", "Type", "X","Y","Status","Storage"),
    (4, "Robot", 3,6,"Idle",0),
    (2, "Robot", 10,6,"Moving",12),
    (5, "Robot", 12,4,"Damage",34),
    (6, "Mine",  13,3,"Working",34),
    (3, "Mine", 13,5,"Full",100),
    (8, "Base", 6,24,"Active",23),
    (7, "Storage", 13,133,"Full",100),
    (1, "Mine", 123,45,"Working",23),
]

COMMANDS = ["Robot commands","Move", "Mine", "Deposit", "Repair", "Scan",]

class KaivosAIApp(App):
    """A Textual app for KaivosAI game."""

    CSS_PATH = "kaivosai.tcss"


    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "toggle_pause", "Pause/Resume"),
    ]

    def __init__(self):
        super().__init__()
        self.dbconn = database.get_connection()
        database.init_game_db(self.dbconn)
        self.map: Static
        self.commands: DataTable
        self.objects: DataTable
        self.events: Static
        self.game_loop: GameLoop
        self.game_worker = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)
        yield Footer()
        self.map = Static(classes="box", id="map")
        self.commands = DataTable(classes="box", id="commands")
        self.objects = DataTable(classes="box", id="objects")
        self.events = Static(classes="box", id="events")
        yield self.map
        yield self.commands
        yield self.objects
        yield self.events
    
    async def on_mount(self) -> None:
        """Mount the app and start the background game loop."""
        # Call parent's on_mount methods
        self.title = "KaivosAI v" + VERSION
        self.map.border_title = "Map"
        self.commands.border_title = "Commands"
        self.objects.border_title = "Objects"
        self.events.border_title = "Events"

        self.objects.add_columns(*OBJECTS[0])
        self.objects.cursor_type = "row"
        for row in OBJECTS[1:]:
            styled_row = [
                Text(str(cell), style="italic #03AC13", justify="right") for cell in row
            ]
            self.objects.add_row(*styled_row)

        self.commands.add_columns(*COMMANDS[0])
        self.commands.cursor_type = "row"
        for row in COMMANDS[1:]:
            styled_row = [
                Text(str(cell), style="italic #03AC13", justify="right") for cell in row
            ]
            self.commands.add_row(*styled_row)
        
        # Start background game loop
        self.game_loop = GameLoop(self, self.dbconn, tick_rate=1.0)
        self.game_worker = self.run_worker(self.game_loop.run(), exclusive=False)
        database.log_event(self.dbconn, "app_start", "KaivosAI application started")
    
    async def update_game_ui(self) -> None:
        """Called by game loop to refresh UI with current game state."""
        # Update status/tick display
        if self.events:
            status = "PAUSED" if self.game_loop.paused else "RUNNING"
            self.events.update(
                f"[bold cyan]Status:[/bold cyan] {status}\n"
                f"[bold cyan]Tick:[/bold cyan] {self.game_loop.tick_count}\n"
                f"[bold cyan]Time:[/bold cyan] {self.game_loop.last_tick_time.strftime('%H:%M:%S')}"
            )
    
    def action_toggle_pause(self) -> None:
        """Toggle game pause state."""
        if self.game_loop.paused:
            self.game_loop.resume()
        else:
            self.game_loop.pause()
    
    def action_quit(self) -> None:
        """Quit the application."""
        # Stop game loop if it exists
        if hasattr(self, 'game_loop') and self.game_loop:
            self.game_loop.stop()
        
        # Cancel the worker if it exists
        if hasattr(self, 'game_worker') and self.game_worker:
            self.game_worker.cancel()
        
        self.exit()

def main():
    """Run the KaivosAI application."""
    app = KaivosAIApp()
    app.run()


if __name__ == "__main__":
    main()
