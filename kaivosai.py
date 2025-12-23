"""KaivosAI - Main entry point with Textual TUI."""

from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static,ListView,ListItem,DataTable

from version import VERSION

ROWS = [
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

class KaivosAIApp(App):
    """A Textual app for KaivosAI game."""

    CSS_PATH = "kaivosai.tcss"


    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)
        yield Footer()
        self.map = Static(classes="box", id="map")
        self.commands = Static(classes="box", id="commands")
        self.objects = DataTable(classes="box", id="objects")
        self.events = Static(classes="box", id="events")
        yield self.map
        yield self.commands
        yield self.objects
        yield self.events

    def on_mount(self) -> None:
        self.map.border_title = "Map"
        self.commands.border_title = "Commands"
        self.objects.border_title = "Objects"
        self.events.border_title = "Events"


        self.objects.add_columns(*ROWS[0])
        self.objects.cursor_type = "row"
        for row in ROWS[1:]:
            # Adding styled and justified `Text` objects instead of plain strings.
            styled_row = [
                Text(str(cell), style="italic #03AC13", justify="right") for cell in row
            ]
            self.objects.add_row(*styled_row)


def main():
    """Run the KaivosAI application."""
    app = KaivosAIApp()
    app.run()


if __name__ == "__main__":
    main()
