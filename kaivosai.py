"""KaivosAI - Main entry point with Textual TUI."""

import asyncio
import sqlite3
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ListView, ListItem, DataTable, Log, Button
from textual.containers import HorizontalGroup, VerticalScroll, Container

import database
import map
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

BUTTON_NAMES = ["Save", "Load", "Reset"]

class GameSettingsList(DataTable):

    def __init__(self, id: str = None):
        super().__init__(id=id)
        self.dbconn = database.get_connection()
    
    def on_mount(self) -> None:
        self.add_columns("Setting", "Value")
        self.cursor_type = "row"
        self.update_list()

    def update_list(self):
        """Fetch and display game settings from database."""
        try:
            # Get all game settings from database
            cur = self.dbconn.execute("SELECT key, value FROM game_settings ORDER BY key")
            settings = cur.fetchall()
            
            # Clear the panel
            self.clear()
            
            if not settings:
                # Add empty row if no settings
                self.add_row("(no settings)", "")
                return
            
            # Display each setting
            for setting in settings:
                key = setting[0] if isinstance(setting, tuple) else setting["key"]
                value = setting[1] if isinstance(setting, tuple) else setting["value"]
                
                styled_row = [
                    Text(str(key), style="bold"),
                    Text(str(value), style="italic #03AC13")
                ]
                self.add_row(*styled_row)
        except Exception as e:
            self.clear()
            self.add_row("Error", str(e))


class GameSettingsPanel(Container):
    """Custom container with settings list and control buttons."""

    def compose(self) -> ComposeResult:
        """Compose the game settings panel with list and buttons."""
        yield GameSettingsList(id="gamesettingsList")
        with HorizontalGroup(id="settingsButtonGroup"):
            for button_name in BUTTON_NAMES:
                yield Button(button_name, id=f"btn_{button_name.lower()}", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        button_id = event.button.id
        button_name = event.button.label
        # Send message to app to handle the button click
        self.app.handle_settings_button(button_name)
                

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
        # Create or load map from database
        self.game_map = map.Map(conn=self.dbconn)

        self.mapPanel: Static
        self.commandsPanel: DataTable
        self.objectsPanel: DataTable
        self.eventsPanel: Log
        self.statusPanel: Static
        self.gamesettingsPanel: GameSettingsPanel
        self.game_loop: GameLoop
        self.game_worker = None
        # Cache the latest event id to avoid unnecessary redraws
        self._last_event_id = None
        # Cache game settings hash to detect changes
        self._last_game_settings_hash = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)
        yield Footer()
        self.mapPanel = Static(classes="panel", id="mapPanel")
        self.commandsPanel = DataTable(classes="panel", id="commandsPanel")
        self.objectsPanel = DataTable(classes="panel", id="objectsPanel")
        self.eventsPanel = Log(classes="panel", id="eventsPanel")
        self.statusPanel = Static(classes="panel", id="statusPanel")
        self.gamesettingsPanel = GameSettingsPanel(id="gamesettingsPanel", classes="panel")
        yield self.mapPanel
        yield self.commandsPanel
        yield self.objectsPanel
        yield self.eventsPanel
        yield self.statusPanel
        yield self.gamesettingsPanel

    def on_ready(self) -> None:
        """Called when the app is ready - start the game loop."""
        self.game_loop = GameLoop(self, self.dbconn, tick_rate=1.0)
        self.game_worker = asyncio.create_task(self.game_loop.run())
        database.log_event(self.dbconn, "app_start", "KaivosAI application started")
        # Force initial events render so panel isn't empty at startup
        try:
            self._update_events_display()
            self._last_event_id = database.get_latest_event_id(self.dbconn)
        except Exception:
            pass
    
    def on_mount(self) -> None:
        """Mount the app and start the background game loop."""
        # Call parent's on_mount methods
        self.title = "KaivosAI v" + VERSION
        self.mapPanel.border_title = "Map"
        
        self.eventsPanel.border_title = "Events"

        self.statusPanel.border_title = "Status"
        self.objectsPanel.add_columns(*OBJECTS[0])
        self.objectsPanel.cursor_type = "row"
        for row in OBJECTS[1:]:
            styled_row = [
                Text(str(cell), style="italic #03AC13", justify="right") for cell in row
            ]
            self.objectsPanel.add_row(*styled_row)

        self.commandsPanel.border_title = "Commands"
        self.commandsPanel.add_columns(*COMMANDS[0])
        self.commandsPanel.cursor_type = "row"
        for row in COMMANDS[1:]:
            styled_row = [
                Text(str(cell), style="italic #03AC13", justify="right") for cell in row
            ]
            self.commandsPanel.add_row(*styled_row)
        
        self.gamesettingsPanel.border_title = "Game Settings"
    
    def update_game_ui(self) -> None:
        """Called by game loop to refresh UI with current game state."""
        # Update status/tick display
        if self.statusPanel:
            status = "PAUSED" if self.game_loop.paused else "RUNNING"
            self.statusPanel.update(
                f"[bold cyan]Status:[/bold cyan] {status}\n"
                f"[bold cyan]Tick:[/bold cyan] {self.game_loop.tick_count}\n"
                f"[bold cyan]Time:[/bold cyan] {self.game_loop.last_tick_time.strftime('%H:%M:%S')}"
            )
        
        # Update events panel only if there are new events
        self._update_events_display_if_needed()
    
    def action_toggle_pause(self) -> None:
        """Toggle game pause state."""
        if self.game_loop.paused:
            self.game_loop.resume()
        else:
            self.game_loop.pause()
    
    def handle_settings_button(self, button_name: str) -> None:
        """Handle settings panel button presses."""
        database.log_event(self.dbconn, "button_pressed", f"Settings button pressed: {button_name}")
        
        if button_name == "Save":
            # TODO: Implement save logic
            self._update_events_display()
        elif button_name == "Load":
            # TODO: Implement load logic
            self._update_events_display()
        elif button_name == "Reset":
            # TODO: Implement reset logic
            self._update_events_display()
    
    def _update_events_display(self) -> None:
        """Fetch and display recent events from database in eventsPanel."""
        if not self.eventsPanel:
            return
        
        try:
            # Get 100 most recent events from database
            events = database.get_recent_events(self.dbconn, limit=100)
            
            # Clear the panel and write events
            self.eventsPanel.clear()
            
            if not events:
                self.eventsPanel.write("No events yet")
                return
            
            # Display each event
            for event in events:
                # Rows are sqlite3.Row so keys are available
                timestamp = event["timestamp"] if "timestamp" in event.keys() else None
                event_type = event["event_type"] if "event_type" in event.keys() else event[2]
                message = event["message"] if "message" in event.keys() else event[3]

                # Fallback timestamp formatting
                ts_display = timestamp if timestamp else "(no time)"
                self.eventsPanel.write_line(f"[{ts_display}] {event_type}: {message}")
                
        except Exception as e:
            self.eventsPanel.clear()
            self.eventsPanel.write_line(f"Error loading events: {str(e)}")
    
    def _update_events_display_if_needed(self) -> None:
        """Refresh events panel only when new events exist."""
        try:
            latest_id = database.get_latest_event_id(self.dbconn)
        except Exception:
            # On query error, fallback to full redraw
            latest_id = None

        # If no change, skip redraw
        if latest_id is not None and latest_id == self._last_event_id:
            return

        # Redraw and update cache
        self._update_events_display()
        self._last_event_id = latest_id

    
    def on_unmount(self) -> None:
        """Clean up resources before app shuts down."""
        # Stop game loop if it exists
        if hasattr(self, 'game_loop') and self.game_loop:
            self.game_loop.stop()
        
        # Cancel the worker if it exists
        if hasattr(self, 'game_worker') and self.game_worker:
            self.game_worker.cancel()

        # Persist map settings and any objects
        if hasattr(self, 'game_map') and self.game_map:
            try:
                self.game_map.save_to_db()
            except Exception:
                pass
        
        # Close database connection
        if hasattr(self, 'dbconn') and self.dbconn:
            database.log_event(self.dbconn, "app_stop", "KaivosAI application stopped")
            self.dbconn.close()

def main():
    """Run the KaivosAI application."""
    app = KaivosAIApp()
    app.run()


if __name__ == "__main__":
    main()
