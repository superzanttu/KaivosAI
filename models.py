"""Game object models for KaivosAI mining simulation.

Defines all game entities: buildings (Mine, Storage, Base), robots, and terrain.
Uses dataclasses for efficient object creation and serialization.
"""

from dataclasses import dataclass
from typing import Tuple, Optional

Position = Tuple[int, int]


@dataclass
class BaseObject:
    id: int = None
    def on_tick(self, tick_count: int, delta_seconds: float, game_map, dbconn) -> None:
        """Tikkikutsu jokaiselle objektityypille.

        Kutsutaan kerran jokaisessa pelisilmukan kierrossa. Oletusimplementaatio
        ei tee mitään; yksittäiset objektit voivat ylikirjoittaa tämän
        ohjatakseen omaa käyttäytymistään.

        Args:
            tick_count: Kokonaisluku, pelitickien kumulatiivinen määrä
            delta_seconds: Kuinka monta sekuntia kului edellisestä tickistä
            game_map: Viittaus aktiiviseen kartta-olioon (Map)
            dbconn: Tietokantayhteys mahdollisia lokituksia/tallennuksia varten
        """
        return None


@dataclass
class BaseBuildingObject(BaseObject):
    name: str = ""
    pos: Position = (0, 0)

@dataclass
class BaseMovingObject(BaseObject):
    name: str = ""
    pos: Position = (0, 0)

@dataclass
class BaseTerrainObject(BaseObject):
    name: str = ""
    pos: Position = (0, 0)


@dataclass
class Mine(BaseBuildingObject):

    name: str = "Mine"
    symbol: str = "M"
    material_stored: int = 0
    material_capacity: int = 10
    _production_time_acc: float = 0.0

    def on_tick(self, tick_count: int, delta_seconds: float, game_map, dbconn) -> None:
        """Kaivoksen tikkipäivitys.

        Tuottaa 1 yksikön materiaalia joka 10 sekunti kunnes kapasiteetti on täynnä.
        """
        try:
            if self.material_stored >= self.material_capacity:
                return
            # Kokoa aikaa ja tuota kun ylittää 10s
            self._production_time_acc += float(delta_seconds or 0.0)
            while self._production_time_acc >= 10.0 and self.material_stored < self.material_capacity:
                self.material_stored += 1
                self._production_time_acc -= 10.0
        except Exception:
            # Varmuuden vuoksi älä kaada peliä
            pass


@dataclass
class Storage(BaseBuildingObject):

    name: str = "Storage"
    symbol: str = "S"
    material_stored: int = 0
    material_capacity: int = 10

    def on_tick(self, tick_count: int, delta_seconds: float, game_map, dbconn) -> None:
        """Varaston tikkipäivitys (ei implementoitu)."""
        return None


@dataclass
class Base(BaseBuildingObject):
 
    name: str = "Base"
    symbol: str = "B"
    material_stored: int = 0
    material_capacity: int = 10

    def on_tick(self, tick_count: int, delta_seconds: float, game_map, dbconn) -> None:
        """Tukikohdan tikkipäivitys (ei implementoitu)."""
        return None


@dataclass
class Robot(BaseMovingObject):
    """Robotti - liikkuva yksikkö joka suorittaa RoboBASIC-ohjelmaa.
    
    Jokaisella robotilla on oma RoboBASIC VM-instanssi (self.vm),
    joka suorittaa robotin omaa ohjelmaa (program_text) täysin itsenäisesti
    muista roboteista.
    
    Attributes:
        name: Robotin nimi
        symbol: Karttasymboli ('R')
        pos: Sijainti kartalla (x, y)
        material_stored: Varastoidun materiaalin määrä
        material_capacity: Maksimikapasiteetti
        program_text: RoboBASIC-ohjelmakoodi
        program_counter: Ohjelman suorituskohta (rivinumero)
        execution_mode: Suoritustila ("STOP", "RUN", "ERROR")
        state: Robotin tila ("IDLE", "MOVING", "LOADING", jne.)
        target: Liikkumiskohde (x, y) tai None
        vm: RoboBASIC-virtuaalikone (luodaan __post_init__:ssä)
    """
 
    name: str = "Robot"
    symbol: str = "R"
    pos: Position = (0, 0)
    material_stored: int = 0
    material_capacity: int = 10
    program_text: str = ""  # RoboBASIC-koodi
    program_counter: int = 0  # Ohjelman suorituskohta
    execution_mode: str = "STOP"  # Suoritustila: "STOP", "RUN", "ERROR"
    state: str = "IDLE"  # Robotin tila: "IDLE", "MOVING", "LOADING", "UNLOADING", jne.
    target: Position = None  # Liikkumiskohde
    
    # VM-instanssi ei ole dataclass-kenttä, alustetaan __post_init__:ssä
    def __post_init__(self):
        """Alusta robotin oma RoboBASIC VM-instanssi.
        
        Kutsutaan automaattisesti dataclass-konstruktorin jälkeen.
        Luo robotille oman VM:n joka suorittaa vain tämän robotin ohjelmaa.
        """
        from robobasic import RoboBASICVM
        self.vm = RoboBASICVM(self)

    def on_tick(self, tick_count: int, delta_seconds: float, game_map, dbconn) -> None:
        """Robotin tikkipäivitys - suorittaa RoboBASIC-ohjelmaa.

        Kutsuu robotin omaa VM:ää suorittamaan yhden tikin verran ohjelmaa.
        
        Args:
            tick_count: Pelitikkien kokonaismäärä
            delta_seconds: Aika edellisestä tikistä
            game_map: Karttaobjekti
            dbconn: Tietokantayhteys
        """
        # Suorita yksi tikki robotin omalla VM:llä
        if hasattr(self, 'vm') and self.vm is not None:
            self.vm.tick(game_map)


@dataclass
class Rock(BaseTerrainObject):
    """Impassable terrain obstacle.
    
    Blocks robot movement and pathfinding.
    Used for terrain generation and map obstacles.
    """
    symbol: str = "#"
    pass


def create_object(obj_type: str, id: int = None, name: str = None, **kwargs):
    """Factory function for creating game objects from type string.
    
    Args:
        obj_type: Object type ('robot', 'mine', 'storage', 'base', 'rock')
        id: Unique identifier (optional)
        name: Display name (optional, will generate default if None)
        **kwargs: Additional fields passed to object constructor
        
    Returns:
        New instance of requested object type
        
    Raises:
        ValueError: If obj_type is not recognized
        
    Example:
        >>> robot = create_object('robot', id=1, pos=(5, 7), capacity=10)
        >>> mine = create_object('mine', name='Iron Mine', pos=(3, 4))
    """
    t = obj_type.lower()
    if t == 'robot':
        return Robot(
            id=id,
            pos=kwargs.get('pos', (0, 0)),
            material_capacity=kwargs.get('material_capacity', 10),
            program_text=kwargs.get('program_text', ''),
        )
    if t == 'mine':
        return Mine(
            id=id,
            name=name or 'Mine',
            pos=kwargs.get('pos', (0, 0)),
            material_capacity=kwargs.get('material_capacity', 10),
            material_stored=kwargs.get('material_stored', 0)
        )
    if t == 'storage':
        return Storage(
            id=id,
            name=name or 'Storage',
            pos=kwargs.get('pos', (0, 0)),
            material_capacity=kwargs.get('material_capacity', 20),
            material_stored=kwargs.get('material_stored', 0)
        )
    if t == 'base':
        return Base(
            id=id,
            name=name or 'Base',
            pos=kwargs.get('pos', (0, 0)),
            material_capacity=kwargs.get('material_capacity', 10),
            material_stored=kwargs.get('material_stored', 0)
        )
    if t == 'rock':
        return Rock(id=id, name=name or 'Rock', pos=kwargs.get('pos', (0, 0)))
    raise ValueError('Unknown object type')
