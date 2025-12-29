"""KaivosAI - Main entry point with Textual TUI."""

import asyncio
import sqlite3
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import (
    Header,
    Footer,
    Static,
    ListView,
    ListItem,
    DataTable,
    Log,
    Button,
)
from textual.containers import HorizontalGroup, VerticalScroll, Container

import database
import map
from version import VERSION
import exceptions
from gameloop import GameLoop

OBJECT_COLUMNS = (
    "ID",
    "Tyyppi",
    "Nimi",
    "X",
    "Y",
    "Varasto",
    "Kapasiteetti",
)

COMMANDS = [
    "Robot commands",
    "Move",
    "Mine",
    "Deposit",
    "Repair",
    "Scan",
]

BUTTON_NAMES = [
    "ResetMap",
    "AddBuildings",
    "Free1",
    "Free2",
]


class GameSettingsList(DataTable):
    """Asetuslistanäkymä."""

    def on_mount(self) -> None:
        """Alustus: käytä jaettua tietokantayhteyttä."""
        self.dbconn = self.app.dbconn
        self.add_columns("Setting", "Value")
        self.cursor_type = "row"
        self.update_list()

    def update_list(self):
        """Hae ja näytä peliasetukset tietokannasta."""
        try:
            # Hae kaikki asetukset tietokannasta
            settings = database.get_all_settings(self.dbconn)

            # Tyhjennä paneeli
            self.clear()

            if not settings:
                # Lisää tyhjä rivi jos ei asetuksia
                self.add_row("(ei asetuksia)", "")
                return

            # Näytä jokainen asetus
            for setting in settings:
                key = setting[0] if isinstance(setting, tuple) else setting["key"]
                value = setting[1] if isinstance(setting, tuple) else setting["value"]

                styled_row = [
                    Text(str(key), style="bold"),
                    Text(str(value), style="italic #03AC13"),
                ]
                self.add_row(*styled_row)
        except Exception as e:
            self.clear()
            self.add_row("Error", str(e))


class GameSettingsPanel(Container):
    """Asetuspaneeli: sisältää asetuslistauksen ja hallintanapit."""

    def compose(self) -> ComposeResult:
        """Luo paneelin komponentit."""
        yield GameSettingsList(id="gamesettingsList")
        with HorizontalGroup(id="settingsButtonGroup"):
            for button_name in BUTTON_NAMES:
                yield Button(
                    button_name, id=f"btn_{button_name.lower()}", variant="primary"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Käsittele nappulan painallus."""
        button_id = event.button.id
        button_name = event.button.label
        # Lähetä viesti sovellukselle käsittelyyn
        self.app.handle_settings_button(button_name)


class GameMapPanel(DataTable):
    """Karttanäkymä: näyttää pelikartan ruudukkona."""

    def on_mount(self):
        """Alustus: aseta solukohdistin ja riviotsikot."""
        self.cursor_type = "cell"
        try:
            self.show_row_labels = True
        except Exception:
            pass

    def refresh_from_map(self):
        """Päivitä karttanäkymä muistissa olevasta Map.cells-rakenteesta.

        Rakentaa ruudukon objekteista luotettavaa näyttöä varten.
        """
        from rich.text import Text

        # Tyhjennä taulukko (sarakkeet mukaan lukien)
        try:
            self.clear(columns=True)
        except Exception:
            self.clear()

        # Hae kartan koko
        full_width = getattr(self.app.game_map, "width", 0) or 0
        full_height = getattr(self.app.game_map, "height", 0) or 0

        # Tarkista että mitat ovat kelvollisia
        if full_width <= 0 or full_height <= 0:
            self.add_column("X", key=0)
            self.add_row("Ei karttaa", key=0, label="0")
            return

        # Näytä koko kartta
        width = full_width
        height = full_height

        # Lue objektit kartan rajapinnan kautta
        objects_dict = self.app.game_map.get_viewport_objects(width, height)

        # Luo sarakkeet vuorotellen värillä luettavuuden parantamiseksi
        for x in range(width):
            # Vaihda väri parillisille sarakkeille
            if x % 2 == 0:
                col_label = Text(str(x), style="bold yellow")
            else:
                col_label = Text(str(x), style="dim white")
            self.add_column(col_label, key=x)

        # Rakenna rivit objektien kanssa
        marked_count = 0
        for y in range(height):
            row_data = []
            for x in range(width):
                if (x, y) in objects_dict:
                    # Objekti tässä paikassa
                    obj_type = objects_dict[(x, y)]
                    if obj_type == "rock":
                        # Tarkista naapurit jotta kivet näyttävät yhtenäisiltä
                        neighbors = {
                            "up": (x, y - 1) in objects_dict
                            and objects_dict.get((x, y - 1)) == "rock",
                            "down": (x, y + 1) in objects_dict
                            and objects_dict.get((x, y + 1)) == "rock",
                            "left": (x - 1, y) in objects_dict
                            and objects_dict.get((x - 1, y)) == "rock",
                            "right": (x + 1, y) in objects_dict
                            and objects_dict.get((x + 1, y)) == "rock",
                        }

                        # Valitse sopiva box-drawing merkki naapureiden perusteella
                        if neighbors["left"] or neighbors["right"]:
                            rock_char = "██"  # Vaakasuora yhtenäinen
                        else:
                            rock_char = "██"  # Pystysuora yhtenäinen

                        row_data.append(Text(rock_char, style="bold white"))
                    elif obj_type == "robot":
                        row_data.append(Text("🤖", style="bold cyan"))
                    elif obj_type == "mine":
                        row_data.append(Text("⛏ ", style="bold yellow"))
                    elif obj_type == "storage":
                        row_data.append(Text("📦", style="bold green"))
                    elif obj_type == "base":
                        row_data.append(Text("🏠", style="bold magenta"))
                    else:
                        row_data.append(Text("? ", style="bold red"))
                    marked_count += 1
                else:
                    # Tyhjä solu (2 merkkiä)
                    row_data.append(Text("··", style="dim"))

            # Lisää rivi otsikoilla - vaihda väri parillisille riveille
            if y % 2 == 0:
                row_label = Text(str(y), style="bold yellow")
            else:
                row_label = Text(str(y), style="dim white")

            try:
                self.add_row(*row_data, key=y, label=row_label)
            except Exception:
                self.add_row(*row_data, key=y)

        # Kirjaa onnistunut päivitys
        import database

        database.log_event(
            self.app.dbconn,
            "map_refresh",
            f"Kartta näytetty: {marked_count} objektia {width}x{height} ruudukossa",
        )


class KaivosAIApp(App):
    """KaivosAI-pelin päätekstuaalinen käyttöliittymä."""

    CSS_PATH = "kaivosai.tcss"

    BINDINGS = [
        ("q", "quit", "Lopeta"),
        ("p", "toggle_pause", "Tauko/Jatka"),
    ]

    def __init__(self):
        """Alustus: luo tietokantayhteys ja lataa kartta."""
        super().__init__()
        self.dbconn = database.get_connection()
        database.init_game_db(self.dbconn)
        # Luo tai lataa kartta tietokannasta
        self.game_map = map.Map(conn=self.dbconn)

        self.mapPanel: GameMapPanel
        self.commandsPanel: DataTable
        self.objectsPanel: DataTable
        self.eventsPanel: Log
        self.statusPanel: Static
        self.gamesettingsPanel: GameSettingsPanel

        self.game_loop: GameLoop
        self.game_worker = None

        # Välimuisti viimeisimmän tapahtuman ID:lle turhien päivitysten välttämiseksi
        self._last_event_id = None

    def compose(self) -> ComposeResult:
        """Luo sovelluksen komponentit."""
        yield Header(show_clock=True)
        yield Footer()
        self.mapPanel = GameMapPanel(classes="panel", id="mapPanel")
        self.commandsPanel = DataTable(classes="panel", id="commandsPanel")
        self.objectsPanel = DataTable(classes="panel", id="objectsPanel")
        self.eventsPanel = Log(classes="panel", id="eventsPanel")
        self.statusPanel = Static(classes="panel", id="statusPanel")
        self.gamesettingsPanel = GameSettingsPanel(
            classes="panel", id="gamesettingsPanel"
        )

        yield self.mapPanel
        yield self.commandsPanel
        yield self.objectsPanel
        yield self.eventsPanel
        yield self.statusPanel
        yield self.gamesettingsPanel

    def on_ready(self) -> None:
        """Kutsutaan kun sovellus on valmis - käynnistä pelisilmukka."""
        # Kirjaa kartan tila käynnistyksessä
        database.log_event(
            self.dbconn,
            "map_load",
            f"Kartta ladattu: {self.game_map.object_count()} objektia muistissa",
        )

        self.game_loop = GameLoop(self, self.dbconn, tick_rate=1.0)
        self.game_worker = asyncio.create_task(self.game_loop.run())
        database.log_event(self.dbconn, "app_start", "KaivosAI käynnistetty")

        # Pakota tapahtumapaneelin alkuperäinen renderöinti
        try:
            self._update_events_display()
            self._last_event_id = database.get_latest_event_id(self.dbconn)
        except Exception:
            pass

        # Alusta kartta kivilla jos tyhjä (objektit ladattu Map.__init__:ssa)
        if self.game_map.is_empty():
            try:
                # Generoi reunakivet ja maastokivet
                border_rocks = self.game_map.generate_border_rocks()
                terrain_rocks = self.game_map.generate_terrain_rocks(
                    density=0.05, cluster_size=4
                )
                database.log_event(
                    self.dbconn,
                    "map_init",
                    f"Kartta alustettu: {border_rocks} reunakiveä, {terrain_rocks} maastokiveä",
                )
            except Exception as e:
                database.log_event(
                    self.dbconn,
                    "map_init_error",
                    f"Virhe kartan alustuksessa: {str(e)}",
                )

        # Näytä kartta muistista
        try:
            self.mapPanel.refresh_from_map()
            self.refresh_objects_panel()
        except Exception as e:
            database.log_event(
                self.dbconn,
                "map_display_error",
                f"Virhe kartan näyttämisessä: {str(e)}",
            )

    def on_mount(self) -> None:
        """Liitä sovellus ja aseta otsikot."""
        self.title = "KaivosAI v" + VERSION
        self.mapPanel.border_title = "Map"

        self.eventsPanel.border_title = "Events"

        self.statusPanel.border_title = "Status"
        self.objectsPanel.border_title = "Objects"
        self.objectsPanel.cursor_type = "row"
        self.refresh_objects_panel()

        self.commandsPanel.border_title = "Commands"
        self.commandsPanel.add_columns(*COMMANDS[0])
        self.commandsPanel.cursor_type = "row"
        for row in COMMANDS[1:]:
            styled_row = [
                Text(str(cell), style="italic #03AC13", justify="right") for cell in row
            ]
            self.commandsPanel.add_row(*styled_row)

        self.gamesettingsPanel.border_title = "Game Settings"

    def refresh_objects_panel(self) -> None:
        """Päivitä objects-paneeli kartalla olevilla roboteilla ja rakennuksilla."""
        if not self.objectsPanel:
            return

        try:
            self.objectsPanel.clear(columns=True)
        except Exception:
            try:
                self.objectsPanel.clear()
            except Exception:
                return

        # Lisää otsikot uudelleen
        self.objectsPanel.add_columns(*OBJECT_COLUMNS)

        # Hae objektit kartalta
        try:
            objects = self.game_map.list_objects()
        except Exception:
            objects = []

        if not objects:
            self.objectsPanel.add_row("-", "-", "-", "-", "-", "-", "-")
            return

        type_styles = {
            "robot": "bold cyan",
            "mine": "bold yellow",
            "storage": "bold green",
            "base": "bold magenta",
        }

        for obj in objects:
            obj_type = obj.get("type", "?")
            row = [
                Text(str(obj.get("id", "")) or "-", style="dim", justify="right"),
                Text(obj_type.capitalize(), style=type_styles.get(obj_type, "white")),
                Text(str(obj.get("name", "-")), style="bold white"),
                Text(str(obj.get("x", "-")), style="dim"),
                Text(str(obj.get("y", "-")), style="dim"),
                Text(str(obj.get("material_stored", "-")), style="italic #03AC13"),
                Text(str(obj.get("material_capacity", "-")), style="italic #03AC13"),
            ]
            self.objectsPanel.add_row(*row)

    def update_game_ui(self) -> None:
        """Päivitä käyttöliittymä pelisilmukan kutsumana."""
        # Päivitä tilanäyttö
        if self.statusPanel:
            status = "TAUOLLA" if self.game_loop.paused else "KÄYNNISSÄ"
            self.statusPanel.update(
                f"[bold cyan]Tila:[/bold cyan] {status}\n"
                f"[bold cyan]Tick:[/bold cyan] {self.game_loop.tick_count}\n"
                f"[bold cyan]Aika:[/bold cyan] {self.game_loop.last_tick_time.strftime('%H:%M:%S')}"
            )

        # Päivitä tapahtumapaneeli vain jos on uusia tapahtumia
        self._update_events_display_if_needed()

        # Päivitä objects-paneeli ajantasaisilla tiedoilla
        try:
            self.refresh_objects_panel()
        except Exception:
            pass

    def action_toggle_pause(self) -> None:
        """Vaihda pelin taukotila."""
        if self.game_loop.paused:
            self.game_loop.resume()
        else:
            self.game_loop.pause()

    def handle_settings_button(self, button_name: str) -> None:
        """Käsittele asetuspaneelin nappuloiden painallukset."""
        database.log_event(
            self.dbconn, "button_pressed", f"Painettu nappia: {button_name}"
        )

        if button_name == "ResetMap":
            # Nollaa kartta ja luo uudelleen
            self.game_map.reset()
            border_rocks = self.game_map.generate_border_rocks()
            terrain_rocks = self.game_map.generate_terrain_rocks(
                density=0.05, cluster_size=4
            )
            database.log_event(
                self.dbconn,
                "map_reset",
                f"Kartta nollattu: {border_rocks} reunakiveä, {terrain_rocks} maastokiveä",
            )
            # Päivitä karttapaneeli
            try:
                self.mapPanel.refresh_from_map()
                self.refresh_objects_panel()
            except Exception as e:
                database.log_event(
                    self.dbconn,
                    "map_display_error",
                    f"Virhe kartan päivittämisessä: {str(e)}",
                )

        elif button_name == "AddBuildings":
            # Lisää rakennukset kartalle
            try:
                base_count, mine_count, storage_count = self.game_map.add_initial_buildings()
                database.log_event(
                    self.dbconn,
                    "buildings_added",
                    f"Lisätty {base_count} tukikohta, {mine_count} kaivosta, {storage_count} varastoa",
                )
                # Päivitä karttapaneeli
                self.mapPanel.refresh_from_map()
                self.refresh_objects_panel()
            except ValueError as e:
                database.log_event(
                    self.dbconn,
                    "buildings_error",
                    f"Virhe rakennusten lisäämisessä: {str(e)}",
                )
            except Exception as e:
                database.log_event(
                    self.dbconn,
                    "buildings_error",
                    f"Odottamaton virhe: {str(e)}",
                )

        elif button_name == "Load":
            # TODO: Implement load logic
            self._update_events_display()
        elif button_name == "Reset":
            # TODO: Implement reset logic
            self._update_events_display()

    def _update_events_display(self) -> None:
        """Hae ja näytä viimeisimmät tapahtumat tietokannasta."""
        if not self.eventsPanel:
            return

        try:
            # Hae 100 viimeisintä tapahtumaa
            events = database.get_recent_events(self.dbconn, limit=100)

            # Tyhjennä paneeli ja kirjoita tapahtumat
            self.eventsPanel.clear()

            if not events:
                self.eventsPanel.write("Ei tapahtumia")
                return

            # Näytä jokainen tapahtuma
            for event in events:
                timestamp = event["timestamp"] if "timestamp" in event.keys() else None
                event_type = (
                    event["event_type"] if "event_type" in event.keys() else event[2]
                )
                message = event["message"] if "message" in event.keys() else event[3]

                # Aikaleiman muotoilu
                ts_display = timestamp if timestamp else "(ei aikaa)"
                self.eventsPanel.write_line(f"[{ts_display}] {event_type}: {message}")

        except Exception as e:
            self.eventsPanel.clear()
            self.eventsPanel.write_line(f"Error loading events: {str(e)}")

    def _update_events_display_if_needed(self) -> None:
        """Päivitä tapahtumapaneeli vain jos uusia tapahtumia on."""
        try:
            latest_id = database.get_latest_event_id(self.dbconn)
        except Exception:
            # Virhetilanteessa piirretään kaikki uudelleen
            latest_id = None

        # Jos ei muutoksia, ohita päivitys
        if latest_id is not None and latest_id == self._last_event_id:
            return

        # Päivitä näyttö ja välimuisti
        self._update_events_display()
        self._last_event_id = latest_id

    def on_unmount(self) -> None:
        """Siivoa resurssit ennen sulkemista."""
        # Pysäytä pelisilmukka
        if hasattr(self, "game_loop") and self.game_loop:
            self.game_loop.stop()

        # Peruuta taustaprosessi
        if hasattr(self, "game_worker") and self.game_worker:
            self.game_worker.cancel()

        # Tallenna kartta muistista tietokantaan
        if hasattr(self, "game_map") and self.game_map:
            try:
                obj_count = self.game_map.object_count()
                self.game_map.save_to_db()
                database.log_event(
                    self.dbconn, "map_save", f"Kartta tallennettu: {obj_count} objektia"
                )
            except Exception as e:
                database.log_event(
                    self.dbconn,
                    "map_save_error",
                    f"Virhe kartan tallennuksessa: {str(e)}",
                )

        # Sulje tietokantayhteys
        if hasattr(self, "dbconn") and self.dbconn:
            database.log_event(self.dbconn, "app_stop", "KaivosAI pysäytetty")
            self.dbconn.close()


def main():
    """Käynnistä KaivosAI-sovellus."""
    app = KaivosAIApp()
    app.run()


if __name__ == "__main__":
    main()
