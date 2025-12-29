"""Game object models for KaivosAI mining simulation.

Defines all game entities: buildings (Mine, Storage, Base), robots, and terrain.
Uses dataclasses for efficient object creation and serialization.
"""

from dataclasses import dataclass, field
from symtable import Symbol
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


    # def extract(self, amount: int) -> int:
    #     """Legacy extraction method (deprecated, use withdraw instead).
        
    #     Args:
    #         amount: Number of materials to extract
            
    #     Returns:
    #         Number of materials actually extracted
    #     """
    #     if self.durability <= 0:
    #         return 0
    #     taken = min(amount, self.durability)
    #     self.durability -= taken
    #     return taken
    
    # def produce(self, game_seconds: int) -> int:
    #     """Produce material if production interval elapsed and not full.
        
    #     Production rate: 1 material per 10 seconds.
    #     Stops when stored >= capacity.
        
    #     Args:
    #         game_seconds: Current game time in seconds
            
    #     Returns:
    #         Number of materials produced (0 or 1)
    #     """
    #     if self.stored >= self.capacity:
    #         return 0  # Full, can't produce
            
    #     # Produce 1 material every 10 seconds
    #     production_interval = 10
    #     if game_seconds >= self.last_production_time + production_interval:
    #         self.stored = min(self.stored + 1, self.capacity)
    #         self.last_production_time = game_seconds
    #         return 1
    #     return 0
    
    # def withdraw(self, amount: int) -> int:
    #     """Withdraw material from mine storage.
        
    #     Args:
    #         amount: Number of materials to withdraw
            
    #     Returns:
    #         Number of materials actually withdrawn (limited by stored amount)
    #     """
    #     take = min(self.stored, amount)
    #     self.stored -= take
    #     return take


@dataclass
class Storage(BaseBuildingObject):

    name: str = "Storage"
    symbol: str = "S"
    material_stored: int = 0
    material_capacity: int = 10

    def on_tick(self, tick_count: int, delta_seconds: float, game_map, dbconn) -> None:
        """Varaston tikkipäivitys.

        Paikka tulevalle automaattiselle tasapainotukselle tai ylläpidolle.
        Tällä hetkellä ei tee mitään.
        """
        return None

    # def store(self, amount: int) -> int:
    #     """Store materials up to capacity limit.
        
    #     Args:
    #         amount: Number of materials to store
            
    #     Returns:
    #         Number of materials actually stored (limited by available space)
    #     """
    #     space = self.capacity - self.stored
    #     if space <= 0:
    #         return 0
    #     put = min(space, amount)
    #     self.stored += put
    #     return put

    # def withdraw(self, amount: int) -> int:
    #     """Withdraw materials from storage.
        
    #     Args:
    #         amount: Number of materials to withdraw
            
    #     Returns:
    #         Number of materials actually withdrawn (limited by stored amount)
    #     """
    #     take = min(self.stored, amount)
    #     self.stored -= take
    #     return take


@dataclass
class Base(BaseBuildingObject):
 
    name: str = "Base"
    symbol: str = "B"
    material_stored: int = 0
    material_capacity: int = 10

    def on_tick(self, tick_count: int, delta_seconds: float, game_map, dbconn) -> None:
        """Tukikohdan tikkipäivitys.

        Paikka resurssien kulutukselle, energiankäytölle, yms. logiikalle.
        Tällä hetkellä ei tee mitään.
        """
        return None

    # def deposit(self, amount: int) -> int:
    #     """Deposit materials to base (increments both bank and stored).
        
    #     Args:
    #         amount: Number of materials to deposit
            
    #     Returns:
    #         Number of materials deposited (always equals amount)
    #     """
    #     self.bank += amount
    #     self.stored += amount
    #     return amount
    
    # def consume(self, game_seconds: int) -> int:
    #     """Consume 1 material every 10 seconds if available.
        
    #     Consumption rate: 1 material per 10 seconds.
    #     Stops when stored reaches 0.
        
    #     Args:
    #         game_seconds: Current game time in seconds
            
    #     Returns:
    #         Number of materials consumed (0 or 1)
    #     """
    #     if self.stored <= 0:
    #         return 0
            
    #     consumption_interval = 10
    #     if game_seconds >= self.last_consumption_time + consumption_interval:
    #         consumed = min(1, self.stored)
    #         self.stored -= consumed
    #         self.last_consumption_time = game_seconds
    #         return consumed
    #     return 0


@dataclass
class Robot(BaseMovingObject):
 
    name: str = "Robot"
    symbol: str = "R"
    pos: Position = (0, 0)
    material_stored: int = 0
    material_capacity: int = 10

    def on_tick(self, tick_count: int, delta_seconds: float, game_map, dbconn) -> None:
        """Robotin tikkipäivitys.

        Paikka liikkumiselle, komentosuoritukselle ja siirroille.
        Tällä hetkellä ei tee mitään.
        """
        return None

    
    # commands_text: list = None  # 10 lines, max 20 chars each - RoboBASIC code
    # _loading_from: Optional[object] = None
    # _loading_amount: Optional[int] = None
    # _unloading_to: Optional[object] = None
    # _unloading_amount: Optional[int] = None
    # _last_transfer_time: float = 0.0
    # # RoboBRAIN execution state
    # _program_running: bool = False  # Is program executing?
    # _program_counter: int = 0  # Current line number (0-based)
    # _program_labels: dict = None  # Label name -> line number mapping
    # _parsed_program: list = None  # Parsed commands from robobrain
    # _blocked_until: float = 0.0  # Game seconds when WAIT/movement finishes
    # _message_inbox: list = None  # Received messages [(type, message, timestamp), ...]
    
    # def __post_init__(self):
    #     """Initialize default values for list/dict fields after dataclass construction.
        
    #     Ensures commands_text, program state, and message inbox are properly initialized.
    #     Called automatically after __init__ by dataclass.
    #     """
    #     if self.commands_text is None:
    #         self.commands_text = [''] * 10
    #     if self._program_labels is None:
    #         self._program_labels = {}
    #     if self._parsed_program is None:
    #         self._parsed_program = []
    #     if self._message_inbox is None:
    #         self._message_inbox = []

    # def move_to(self, target: Position):
    #     """Move robot to target position instantly.
        
    #     Args:
    #         target: (x, y) coordinates to move to
        
    #     Note:
    #         Actual pathfinding and timed movement is handled by Map class.
    #         This method just updates the position field.
    #     """
    #     self.pos = target

    # def start_loading(self, source, amount: int = None):
    #     """Initiate loading operation from source object.
        
    #     Transfer executes at 1 material/second via Map.tick_transfer().
    #     Cancels any ongoing unloading operation.
        
    #     Args:
    #         source: Object to load from (Mine, Storage, Base, or Robot)
    #         amount: Target materials to load (None = load until full)
        
    #     Note:
    #         Sets _loading_from and _loading_amount for tick_transfer() to process.
    #         Actual transfer logic is in Map.tick_transfer().
    #     """
    #     # Initialize fields if missing
    #     if not hasattr(self, '_loading_from'):
    #         self._loading_from = None
    #     if not hasattr(self, '_loading_amount'):
    #         self._loading_amount = None
    #     if not hasattr(self, '_unloading_to'):
    #         self._unloading_to = None
    #     if not hasattr(self, '_unloading_amount'):
    #         self._unloading_amount = None
    #     if not hasattr(self, '_last_transfer_time'):
    #         self._last_transfer_time = 0.0
            
    #     # Cancel any ongoing operations
    #     self._unloading_to = None
    #     self._unloading_amount = None
        
    #     # Start loading
    #     free = self.capacity - self.inventory
    #     self._loading_from = source
    #     self._loading_amount = amount if amount is not None else free
        
    # def start_unloading(self, target, amount: int = None):
    #     """Initiate unloading operation to target object.
        
    #     Transfer executes at 1 material/second via Map.tick_transfer().
    #     Cancels any ongoing loading operation.
        
    #     Args:
    #         target: Object to unload to (Storage, Base, or Robot)
    #         amount: Target materials to unload (None = unload all inventory)
        
    #     Note:
    #         Sets _unloading_to and _unloading_amount for tick_transfer() to process.
    #         Actual transfer logic is in Map.tick_transfer().
    #     """
    #     # Initialize fields if missing
    #     if not hasattr(self, '_loading_from'):
    #         self._loading_from = None
    #     if not hasattr(self, '_loading_amount'):
    #         self._loading_amount = None
    #     if not hasattr(self, '_unloading_to'):
    #         self._unloading_to = None
    #     if not hasattr(self, '_unloading_amount'):
    #         self._unloading_amount = None
    #     if not hasattr(self, '_last_transfer_time'):
    #         self._last_transfer_time = 0.0
            
    #     # Cancel any ongoing operations
    #     self._loading_from = None
    #     self._loading_amount = None
        
    #     # Start unloading
    #     self._unloading_to = target
    #     self._unloading_amount = amount if amount is not None else self.inventory
    
    # def load_from(self, source, amount: int = None) -> int:
    #     """Instant load operation (legacy method, prefer start_loading for timed transfer).
        
    #     Args:
    #         source: Object to load from
    #         amount: Materials to load (None = fill to capacity)
            
    #     Returns:
    #         Number of materials actually loaded
            
    #     Note:
    #         This is instant transfer. Use start_loading() for realistic 1/second rate.
    #     """
    #     free = self.capacity - self.inventory
    #     if free <= 0:
    #         return 0
        
    #     load_amount = amount if amount is not None else free
    #     load_amount = min(load_amount, free)
        
    #     # Withdraw from source
    #     if hasattr(source, 'withdraw'):
    #         taken = source.withdraw(load_amount)
    #     elif isinstance(source, Robot):
    #         # Take from another robot's inventory
    #         taken = min(load_amount, source.inventory)
    #         source.inventory -= taken
    #     else:
    #         return 0
        
    #     self.inventory += taken
    #     return taken
    
    # def unload_to(self, target, amount: int = None) -> int:
    #     """Unload material to target object (Storage, Base, or Robot)."""
    #     if self.inventory <= 0:
    #         return 0
        
    #     unload_amount = amount if amount is not None else self.inventory
    #     unload_amount = min(unload_amount, self.inventory)
        
    #     # Deposit to target
    #     if hasattr(target, 'store'):
    #         # Storage
    #         stored = target.store(unload_amount)
    #     elif hasattr(target, 'deposit'):
    #         # Base
    #         stored = target.deposit(unload_amount)
    #     elif isinstance(target, Robot):
    #         # Transfer to another robot
    #         free = target.capacity - target.inventory
    #         stored = min(unload_amount, free)
    #         target.inventory += stored
    #     else:
    #         return 0
        
    #     self.inventory -= stored
    #     return stored

    # def mine(self, mine: Mine, amount: int = None) -> int:
    #     if self.pos != mine.pos:
    #         return 0
    #     free = self.capacity - self.inventory
    #     if free <= 0:
    #         return 0
    #     want = free if amount is None else min(free, amount)
    #     taken = mine.extract(want)
    #     self.inventory += taken
    #     return taken

    # def deposit_to_storage(self, storage: Storage) -> int:
    #     if self.pos != storage.pos:
    #         return 0
    #     deposited = storage.store(self.inventory)
    #     self.inventory -= deposited
    #     return deposited

    # def deposit_to_base(self, base: Base) -> int:
    #     if self.pos != base.pos:
    #         return 0
    #     amount = self.inventory
    #     accepted = base.deposit(amount)
    #     self.inventory -= accepted
    #     return accepted


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
            capacity=kwargs.get('capacity', 5),
            commands_text=kwargs.get('commands_text', None),
        )
    if t == 'mine':
        return Mine(id=id, name=name or 'Mine', pos=kwargs.get('pos', (0, 0)), 
                    durability=kwargs.get('durability', 10), 
                    capacity=kwargs.get('capacity', 10),
                    stored=kwargs.get('stored', 0))
    if t == 'storage':
        return Storage(id=id, name=name or 'Storage', pos=kwargs.get('pos', (0, 0)), 
                       capacity=kwargs.get('capacity', 20),
                       stored=kwargs.get('stored', 0))
    if t == 'base':
        return Base(id=id, name=name or 'Base', pos=kwargs.get('pos', (0, 0)),
                    bank=kwargs.get('bank', 0),
                    stored=kwargs.get('stored', 0))
    if t == 'rock':
        return Rock(id=id, name=name or 'Rock', pos=kwargs.get('pos', (0, 0)))
    raise ValueError('Unknown object type')
