"""Pelimaailman kartta ja objektien hallinta.

Vastaa objektien sijoittelusta, liikkeistä, reitinhaunasta ja pelin tick-logiikasta.
Kaikki pelitilan vuorovaikutus kulkee Map-luokan kautta.

Päävastuut:
    - Sijaintien tallennus (koordinaatit -> objekti)
    - Objektien elinkaari (lisäys, poisto, siirto)
    - Robottien liike reitinhaunalla (BFS-algoritmi)
    - Materiaalien tuotanto ja kulutus
    - Robottien siirtooperaatiot (lastaus/purku)
    - RoboBASIC-ohjelmien suoritus

Säikeistys:
    - Vain pääsäie (ei taustasäikeitä)
    - Kaikki tickit kutsutaan eksplisiittisesti CLI:n refresh_display():sta
    - Käyttää tietokantayhteyttä pääsäikeestä
"""

from typing import Tuple, Dict, Optional, List
import sqlite3
import threading
import time
import random

from database import (
    init_game_db,
    delete_object_db,
    load_objects_from_db,
    log_event,
    get_map_settings,
    save_map_settings,
    clear_all_objects,
    clear_map_settings,
    persist_object,
)
from models import Robot, Mine, Storage, Base, Rock
from exceptions import MapError, ValidationError

Position = Tuple[int, int]


class Map:
    """Pelimaailman kartta hallinnoi kaikkia objekteja ja niiden sijaintisuhteita."""

    def __init__(
        self,
        width: int = 100,
        height: int = 100,
        conn: Optional[sqlite3.Connection] = None,
    ):
        self.width = width
        self.height = height
        self.conn = conn
        self.cells: Dict[Position, object] = {}
        # Alusta tietokannan rakenne jos yhteys annettu
        if self.conn:
            init_game_db(self.conn)
            # Lataa kartan asetukset tietokannasta; käytä oletuksia jos ei löydy
            self._load_map_settings()
            # Lataa olemassa olevat objektit tietokannasta muistiin
            self._load_objects_from_db()

    def _load_map_settings(self) -> None:
        """Lataa kartan mitat game_settings-taulusta, jos olemassa.
        
        Käyttää muistissa olevia oletuksia jos asetuksia ei löydy.
        """
        try:
            settings = get_map_settings(self.conn)
            loaded_from_db = False

            if settings["width"] is not None:
                self.width = settings["width"]
                loaded_from_db = True

            if settings["height"] is not None:
                self.height = settings["height"]
                loaded_from_db = True

            # Kirjaa kartan lataus
            try:
                if loaded_from_db:
                    log_event(
                        self.conn,
                        "map_loaded",
                        f"Map loaded: width={self.width}, height={self.height}",
                    )
                else:
                    log_event(
                        self.conn,
                        "map_loaded",
                        f"Map loaded with defaults: width={self.width}, height={self.height}",
                    )
            except Exception:
                pass
        except Exception:
            # Jos jokin menee pieleen, säilytä oletukset
            pass

    def _load_objects_from_db(self) -> None:
        """Lataa objektit tietokannasta muistiin (self.cells).
        
        Luo uudelleen objekti-instanssit tietokantariveistä ja täyttää cells-sanakirjan.
        """
        if not self.conn:
            return

        try:
            rows = load_objects_from_db(self.conn)
            loaded_count = 0

            for row in rows:
                try:
                    obj_type = row["type"] if "type" in row.keys() else row[1]
                    x = row["x"] if "x" in row.keys() else row[3]
                    y = row["y"] if "y" in row.keys() else row[4]
                    name = row["name"] if "name" in row.keys() else row[2]

                    pos = (int(x), int(y))

                    # Create appropriate object instance
                    if obj_type == "rock":
                        obj = Rock(name=name or "Rock", pos=pos)
                    elif obj_type == "robot":
                        obj = Robot(name=name or "Robot", pos=pos)
                    elif obj_type == "mine":
                        obj = Mine(name=name or "Mine", pos=pos)
                    elif obj_type == "storage":
                        obj = Storage(name=name or "Storage", pos=pos)
                    elif obj_type == "base":
                        obj = Base(name=name or "Base", pos=pos)
                    else:
                        continue  # Skip unknown types

                    self.cells[pos] = obj
                    loaded_count += 1

                except Exception:
                    continue  # Skip malformed rows

            if loaded_count > 0:
                try:
                    log_event(
                        self.conn,
                        "objects_loaded",
                        f"Loaded {loaded_count} objects from database",
                    )
                except Exception:
                    pass

        except Exception:
            # If loading fails, continue with empty map
            pass

    def save_to_db(self) -> None:
        """Tallenna kartan asetukset (leveys/korkeus) ja muistissa olevat objektit tietokantaan.
        
        Huom: Objektien tallennus on parhaansa mukaan käyttäen database.persist_object
        `cells`:ssä oleville objekteille. Tyhjät kartat tallentavat vain mitat.
        """
        if not self.conn:
            return
        try:
            # Begin a single transaction for atomic persistence
            self.conn.execute("BEGIN")

            # Save map dimensions using database API without auto-commit
            save_map_settings(self.conn, self.width, self.height, commit=False)

            # Remove any stale rows so DB mirrors in-memory state
            clear_all_objects(self.conn, commit=False)

            # Persist any objects present in memory without per-object commits
            for pos, obj in list(self.cells.items()):
                try:
                    persist_object(self.conn, obj, commit=False)
                except Exception:
                    # Continue on individual object persist errors
                    continue

            # Commit the full transaction once
            self.conn.commit()

            # Log map save event
            try:
                obj_count = len(self.cells)
                log_event(
                    self.conn,
                    "map_saved",
                    f"Map saved: width={self.width}, height={self.height}, objects={obj_count}",
                )
            except Exception:
                pass
        except Exception:
            # Avoid crashing on exit due to persistence issues
            try:
                self.conn.rollback()
            except Exception:
                pass

    def reset(self) -> None:
        """Nollaa kartta tyhjään tilaan - tyhjennä kaikki objektit muistista ja tietokannasta.
        
        Tyhjentää:
            - Kaikki muistissa olevat solut (objektit-sanakirja)
            - Kaikki objektit tietokannan objects-taulusta
            - Kartan leveys/korkeus asetukset tietokannasta
            - Säilyttää kartan mitat (leveys/korkeus) muistissa
        """
        # Tyhjennä muistissa olevat objektit
        self.cells.clear()

        # Tyhjennä tietokanta käyttäen database API:a
        if self.conn:
            try:
                clear_all_objects(self.conn)
                clear_map_settings(self.conn)
                log_event(
                    self.conn,
                    "map_reset",
                    f"Map reset to empty state. Dimensions: {self.width}x{self.height}",
                )
            except Exception as e:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                try:
                    log_event(
                        self.conn, "map_reset_error", f"Error resetting map: {str(e)}"
                    )
                except Exception:
                    pass

    def add_object(self, obj, pos: Position, persist: bool = True):
        """Lisää objekti karttaan määritettyyn sijaintiin.
        
        Args:
            obj: Lisättävä peliobjekti
            pos: (x, y) sijainti johon objekti sijoitetaan
            persist: Tallennetaanko tietokantaan välittömästi (aseta False massaoperaatioille)
            
        Raises:
            ValueError: Jos sijainti rajojen ulkopuolella tai jo varattu
            
        Huom:
            Tallentaa automaattisesti tietokantaan jos yhteys saatavilla ja persist=True.
            Massaoperaatioille aseta persist=False ja tee commit manuaalisesti jälkikäteen.
        """
        if not self.in_bounds(pos):
            raise ValueError("Position out of bounds")
        if self.is_occupied(pos):
            raise ValueError("Cell is already occupied")
        if hasattr(obj, "pos"):
            obj.pos = pos
        self.cells[pos] = obj
        if self.conn and persist:
            persist_object(self.conn, obj)
        return True

    def object_count(self) -> int:
        """Palauta muistissa olevien objektien määrä."""
        return len(self.cells)

    def is_empty(self) -> bool:
        """Palauta True jos yhtään objektia ei ole tallennettu muistiin."""
        return not self.cells

    def get_viewport_objects(self, width: int, height: int) -> Dict[Position, str]:
        """Palauta sanakirja sijainneista -> tyyppeihin annetulla näkymäalueella.
        
        Args:
            width: näkymäalueen leveys (sarakkeet) alkaen x=0
            height: näkymäalueen korkeus (rivit) alkaen y=0
            
        Returns:
            Sanakirja (x, y) -> pienaakkoset tyyppinimi
        """
        view: Dict[Position, str] = {}
        max_x = min(self.width, width)
        max_y = min(self.height, height)
        for (x, y), obj in self.cells.items():
            if 0 <= x < max_x and 0 <= y < max_y:
                view[(x, y)] = type(obj).__name__.lower()
        return view

    def in_bounds(self, pos: Position) -> bool:
        """Tarkista onko sijainti kartan rajojen sisällä.
        
        Args:
            pos: (x, y) koordinaatit tarkistettavaksi
            
        Returns:
            True jos sijainti on kartan rajojen sisällä
        """
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_occupied(self, pos: Position) -> bool:
        """Tarkista onko sijainnissa objekti.
        
        Args:
            pos: (x, y) koordinaatit tarkistettavaksi
            
        Returns:
            True jos sijainnissa on objekti
        """
        return pos in self.cells

    def generate_border_rocks(self):
        """Generoi kivireuna kartan kaikkien reunojen ympärille.
        
        Returns:
            Lisättyjen kivien määrä
            
        Huom:
            Luo Rock-objektit kaikille neljälle reunalle (ylä/ala/vasen/oikea).
            Ohittaa jo varatut sijainnit.
            Käyttää erätallenusta suorituskyvyn parantamiseksi.
        """
        rocks_added = 0
        # Ylä- ja alareunat
        for x in range(self.width):
            if (x, 0) not in self.cells:
                rock = Rock(name=f"Border Rock", pos=(x, 0))
                self.add_object(rock, (x, 0), persist=False)
                rocks_added += 1
            if (x, self.height - 1) not in self.cells:
                rock = Rock(name=f"Border Rock", pos=(x, self.height - 1))
                self.add_object(rock, (x, self.height - 1), persist=False)
                rocks_added += 1
        # Vasen ja oikea reuna
        for y in range(1, self.height - 1):
            if (0, y) not in self.cells:
                rock = Rock(name=f"Border Rock", pos=(0, y))
                self.add_object(rock, (0, y), persist=False)
                rocks_added += 1
            if (self.width - 1, y) not in self.cells:
                rock = Rock(name=f"Border Rock", pos=(self.width - 1, y))
                self.add_object(rock, (self.width - 1, y), persist=False)
                rocks_added += 1

        # Erätallennus kaikille kiville yhdellä transaktiolla
        if self.conn and rocks_added > 0:
            try:
                self.conn.execute("BEGIN")
                for pos, obj in self.cells.items():
                    if isinstance(obj, Rock):
                        persist_object(self.conn, obj, commit=False)
                self.conn.commit()
            except Exception:
                try:
                    self.conn.rollback()
                except Exception:
                    pass

        return rocks_added

    def _generate_rock_cluster(
        self, start_pos: Position, cluster_size: int
    ) -> List[Position]:
        """Generoi kiviklusteri satunnaiskävelyllä.
        
        Args:
            start_pos: Klusterin aloitussijainti
            cluster_size: Tavoiteltu kivien määrä klusterissa
            
        Returns:
            Lista sijainteja klusterille
        """
        positions = [start_pos]
        current_pos = start_pos

        # Satunnaiskävely luonnollisen näköisen klusterin luomiseksi
        for _ in range(cluster_size - 1):
            # Try to add adjacent position
            x, y = current_pos
            directions = [
                (x + 1, y),
                (x - 1, y),
                (x, y + 1),
                (x, y - 1),
                (x + 1, y + 1),
                (x - 1, y - 1),
                (x + 1, y - 1),
                (x - 1, y + 1),
            ]

            # Filter valid positions
            valid = [
                pos
                for pos in directions
                if self.in_bounds(pos) and pos not in positions
            ]

            if valid:
                # Pick random adjacent cell with bias toward closer cells
                next_pos = random.choice(valid)
                positions.append(next_pos)
                # Sometimes continue from new position, sometimes backtrack
                if random.random() < 0.7:
                    current_pos = next_pos

        return positions

    def generate_terrain_rocks(self, density: float = 0.05, cluster_size: int = 3):
        """Generoi luonnollisen näköisiä kiviformaatioita kartan sisään.
        
        Args:
            density: Todennäköisyys kiviklusterin alkamiselle (0.0 - 1.0, oletus 0.05)
            cluster_size: Kiviklustereiden keskimääräinen koko (oletus 3)
            
        Returns:
            Lisättyjen kivien määrä
            
        Huom:
            - Välttää reunoja (2 solua reunasta)
            - Käyttää satunnaiskävely-algoritmia luonnolliseen klusterointiin
            - Ohittaa varatut sijainnit
            - Tiheys 0.05 = ~5% soluista muuttuu kiviklusteiksi
            - Käyttää erätallenusta suorituskyvyn parantamiseksi
        """
        rocks_added = 0
        added_rocks = []  # Seuraa kiviä erätallenusta varten

        # Vältä reunoja (niissä on jo reunakivet)
        for y in range(2, self.height - 2):
            for x in range(2, self.width - 2):
                # Skip if already occupied
                if (x, y) in self.cells:
                    continue

                # Random chance to start a cluster
                if random.random() < density:
                    # Create a cluster of rocks
                    cluster_positions = self._generate_rock_cluster(
                        (x, y), cluster_size
                    )
                    for pos in cluster_positions:
                        px, py = pos
                        # Check bounds and if position is free
                        if (
                            1 <= px < self.width - 1
                            and 1 <= py < self.height - 1
                            and pos not in self.cells
                        ):
                            rock = Rock(name="Rock", pos=pos)
                            try:
                                self.add_object(rock, pos, persist=False)
                                added_rocks.append(rock)
                                rocks_added += 1
                            except Exception:
                                continue

        # Erätallennus kaikille kiville yhdellä transaktiolla
        if self.conn and added_rocks:
            try:
                self.conn.execute("BEGIN")
                for rock in added_rocks:
                    persist_object(self.conn, rock, commit=False)
                self.conn.commit()
            except Exception:
                try:
                    self.conn.rollback()
                except Exception:
                    pass

        return rocks_added

    def add_initial_buildings(self):
        """Lisää karttaan alkutilat: 1 tukikohta, 10 kaivosta ja 5 varastoa.
        
        Sijoittaa rakennukset satunnaisiin vapaisiin sijainteihin välttäen reunoja
        ja varattuja soluja. Käyttää erätallenusta suorituskyvyn parantamiseksi.
        
        Returns:
            Tuple (base_count, mine_count, storage_count): Lisättyjen rakennusten määrät
            
        Raises:
            ValueError: Jos vapaita sijainteja ei löydy riittävästi
        """
        buildings_added = []
        base_count = 0
        mine_count = 0
        storage_count = 0
        
        # Kerää kaikki vapaat sijainnit (välttäen reunoja)
        free_positions = []
        for y in range(2, self.height - 2):
            for x in range(2, self.width - 2):
                if (x, y) not in self.cells:
                    free_positions.append((x, y))
        
        # Tarkista että on riittävästi tilaa
        required_buildings = 1 + 10 + 5  # tukikohta + kaivokset + varastot
        if len(free_positions) < required_buildings:
            raise ValueError(
                f"Ei tarpeeksi vapaita sijainteja. Tarvitaan {required_buildings}, "
                f"saatavilla {len(free_positions)}"
            )
        
        # Sekoita sijaintilista satunnaisuutta varten
        random.shuffle(free_positions)
        
        # Lisää 1 tukikohta
        pos = free_positions.pop()
        base = Base(name="Base", pos=pos)
        self.add_object(base, pos, persist=False)
        buildings_added.append(base)
        base_count = 1
        
        # Lisää 10 kaivosta
        for i in range(10):
            pos = free_positions.pop()
            mine = Mine(name=f"Mine_{i+1}", pos=pos)
            self.add_object(mine, pos, persist=False)
            buildings_added.append(mine)
            mine_count += 1
        
        # Lisää 5 varastoa
        for i in range(5):
            pos = free_positions.pop()
            storage = Storage(name=f"Storage_{i+1}", pos=pos)
            self.add_object(storage, pos, persist=False)
            buildings_added.append(storage)
            storage_count += 1
        
        # Erätallennus kaikille rakennuksille yhdellä transaktiolla
        if self.conn and buildings_added:
            try:
                self.conn.execute("BEGIN")
                for building in buildings_added:
                    persist_object(self.conn, building, commit=False)
                self.conn.commit()
            except Exception:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
        
        return (base_count, mine_count, storage_count)

    def generate_random_rocks(self, count: int = 50, density: float = 0.05):
        """Generoi satunnaisia kiviä hajallaan kartalle.
        
        Args:
            count: Tavoiteltu kivien määrä (jos tiheyttä ei käytetä)
            density: Osuus kartan soluista täytettäväksi kivillä (0.0 - 1.0)
                    Jos > 0, ohittaa count-parametrin
        
        Returns:
            Onnistuneesti lisättyjen kivien määrä
            
        Huom:
            Ohittaa varatut sijainnit. Käyttää tiheyttä jos määritetty,
            muuten sijoittaa 'count' kiveä satunnaisiin kelvolliisiin sijainteihin.
            Käyttää erätallenusta suorituskyvyn parantamiseksi.
        """
        # Laske tavoitemäärä tiheydestä jos määritetty
        if density > 0:
            total_cells = self.width * self.height
            count = int(total_cells * density)

        rocks_added = 0
        attempts = 0
        max_attempts = count * 10  # Vältä ikuinen silmukka
        added_rocks = []  # Seuraa lisättyjä kiviä erätallenusta varten

        while rocks_added < count and attempts < max_attempts:
            attempts += 1
            # Random position within map bounds
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)

            # Skip if occupied
            if (x, y) in self.cells:
                continue

            # Add rock without immediate persistence
            rock = Rock(name=f"Rock", pos=(x, y))
            try:
                self.add_object(rock, (x, y), persist=False)
                added_rocks.append(rock)
                rocks_added += 1
            except Exception:
                # Skip on error (shouldn't happen but be safe)
                continue

        # Batch persist all rocks in one transaction
        if self.conn and added_rocks:
            try:
                self.conn.execute("BEGIN")
                for rock in added_rocks:
                    persist_object(self.conn, rock, commit=False)
                self.conn.commit()
            except Exception:
                try:
                    self.conn.rollback()
                except Exception:
                    pass

        return rocks_added
