"""Game object models for KaivosAI mining simulation.

Defines all game entities: buildings (Mine, Storage, Base), robots, and terrain.
Uses dataclasses for efficient object creation and serialization.
"""

from dataclasses import dataclass
from typing import Tuple, Optional

Position = Tuple[int, int]


def _ensure_material_fields(obj, stored_default: int = 0, 
                            last_time_field: str = 'last_production_time',
                            last_time_default: float = 0.0) -> None:
    """Ensure material system fields exist for backward compatibility.
    
    Initializes missing material fields on objects loaded from old database
    versions that didn't have these attributes. Prevents AttributeError when
    accessing production/consumption timing fields.
    
    Args:
        obj: Object to initialize fields on
        stored_default: Default value for stored field (typically 0)
        last_time_field: Name of timing field (last_production_time or last_consumption_time)
        last_time_default: Default value for timing field (typically 0.0)
        
    Note:
        Called automatically by produce() and consume() methods.
        Safe to call multiple times (idempotent).
        
    Example:
        >>> mine = Mine(pos=(5, 5))
        >>> _ensure_material_fields(mine)
        >>> mine.stored  # Now safe to access
        0
    """
    if not hasattr(obj, 'stored') or obj.stored is None:
        obj.stored = stored_default
    if not hasattr(obj, 'capacity') or obj.capacity is None:
        obj.capacity = 10
    if not hasattr(obj, last_time_field):
        setattr(obj, last_time_field, last_time_default)


@dataclass
class Building:
    """Base class for all stationary structures in the game world.
    
    Attributes:
        id: Unique identifier (auto-assigned by database)
        name: Human-readable name for display
        pos: (x, y) coordinates on game map
    """
    id: Optional[int] = None
    name: str = ""
    pos: Position = (0, 0)


@dataclass
class Mine(Building):
    """Resource extraction building that produces materials over time.
    
    Produces 1 material every 10 seconds until capacity is reached.
    Materials can be withdrawn by robots for transport to bases.
    
    Attributes:
        ore_type: Type of resource produced (currently unused, for future)
        durability: Legacy field for extraction (deprecated)
        stored: Current material count in storage
        capacity: Maximum materials mine can store
        last_production_time: Game seconds of last production tick
    """
    ore_type: str = "ore"
    durability: int = 10
    stored: int = 0
    capacity: int = 10
    last_production_time: float = 0.0

    def extract(self, amount: int) -> int:
        """Legacy extraction method (deprecated, use withdraw instead).
        
        Args:
            amount: Number of materials to extract
            
        Returns:
            Number of materials actually extracted
        """
        if self.durability <= 0:
            return 0
        taken = min(amount, self.durability)
        self.durability -= taken
        return taken
    
    def produce(self, game_seconds: int) -> int:
        """Produce material if production interval elapsed and not full.
        
        Production rate: 1 material per 10 seconds.
        Stops when stored >= capacity.
        
        Args:
            game_seconds: Current game time in seconds
            
        Returns:
            Number of materials produced (0 or 1)
        """
        # Initialize fields if missing (for objects loaded from old DB)
        _ensure_material_fields(self, last_time_field='last_production_time')
            
        if self.stored >= self.capacity:
            return 0  # Full, can't produce
        # Produce 1 material every 10 seconds
        production_interval = 10
        if game_seconds >= self.last_production_time + production_interval:
            self.stored = min(self.stored + 1, self.capacity)
            self.last_production_time = game_seconds
            return 1
        return 0
    
    def withdraw(self, amount: int) -> int:
        """Withdraw material from mine storage.
        
        Args:
            amount: Number of materials to withdraw
            
        Returns:
            Number of materials actually withdrawn (limited by stored amount)
        """
        take = min(self.stored, amount)
        self.stored -= take
        return take


@dataclass
class Storage(Building):
    """Material storage facility for accumulating resources.
    
    Acts as intermediate storage between mines and bases.
    Robots can load from and unload to storage.
    
    Attributes:
        capacity: Maximum materials storage can hold (default 20)
        stored: Current material count
    """
    capacity: int = 20
    stored: int = 0

    def store(self, amount: int) -> int:
        """Store materials up to capacity limit.
        
        Args:
            amount: Number of materials to store
            
        Returns:
            Number of materials actually stored (limited by available space)
        """
        space = self.capacity - self.stored
        if space <= 0:
            return 0
        put = min(space, amount)
        self.stored += put
        return put

    def withdraw(self, amount: int) -> int:
        """Withdraw materials from storage.
        
        Args:
            amount: Number of materials to withdraw
            
        Returns:
            Number of materials actually withdrawn (limited by stored amount)
        """
        take = min(self.stored, amount)
        self.stored -= take
        return take


@dataclass
class Base(Building):
    """Main base building that consumes materials over time.
    
    Represents the primary objective - keep bases supplied with materials.
    Consumes 1 material every 10 seconds when materials are available.
    Tracks total materials delivered in bank (lifetime counter).
    
    Attributes:
        bank: Cumulative total of all materials delivered (never decreases)
        stored: Current materials available for consumption
        last_consumption_time: Game seconds of last consumption tick
    """
    bank: int = 0
    stored: int = 0
    last_consumption_time: float = 0.0

    def deposit(self, amount: int) -> int:
        """Deposit materials to base (increments both bank and stored).
        
        Args:
            amount: Number of materials to deposit
            
        Returns:
            Number of materials deposited (always equals amount)
        """
        self.bank += amount
        self.stored += amount
        return amount
    
    def consume(self, game_seconds: int) -> int:
        """Consume 1 material every 10 seconds if available.
        
        Consumption rate: 1 material per 10 seconds.
        Stops when stored reaches 0.
        
        Args:
            game_seconds: Current game time in seconds
            
        Returns:
            Number of materials consumed (0 or 1)
        """
        # Initialize fields if missing (for objects loaded from old DB)
        _ensure_material_fields(self, last_time_field='last_consumption_time')
            
        if self.stored <= 0:
            return 0
        consumption_interval = 10
        if game_seconds >= self.last_consumption_time + consumption_interval:
            consumed = min(1, self.stored)
            self.stored -= consumed
            self.last_consumption_time = game_seconds
            return consumed
        return 0


@dataclass
class Robot:
    """Autonomous mobile unit for material transport and task execution.
    
    Robots can move, load/unload materials, and execute RoboBASIC programs.
    Support both manual control (commands) and autonomous operation (RoboBRAIN).
    
    Attributes:
        id: Unique identifier
        pos: Current (x, y) coordinates
        capacity: Maximum materials robot can carry
        inventory: Current material count being carried
        name: Display name
        commands_text: List of 10 RoboBASIC code lines (max 20 chars each)
        
    Transfer State:
        _loading_from: Source object currently loading from
        _loading_amount: Target amount to load
        _unloading_to: Destination object currently unloading to
        _unloading_amount: Target amount to unload
        _last_transfer_time: Game seconds of last transfer tick
        
    RoboBRAIN Execution State:
        _program_running: Is RoboBASIC program currently executing?
        _program_counter: Current line number (0-based)
        _program_labels: Dict mapping label names to line numbers
        _parsed_program: Parsed commands from RoboBASIC parser
        _blocked_until: Game seconds when WAIT/movement finishes
        _message_inbox: Received messages [(sender_type, message, timestamp), ...]
    """
    id: Optional[int] = None
    pos: Position = (0, 0)
    capacity: int = 5
    inventory: int = 0
    name: str = "Robot"
    commands_text: list = None  # 10 lines, max 20 chars each - RoboBASIC code
    _loading_from: Optional[object] = None
    _loading_amount: Optional[int] = None
    _unloading_to: Optional[object] = None
    _unloading_amount: Optional[int] = None
    _last_transfer_time: float = 0.0
    # RoboBRAIN execution state
    _program_running: bool = False  # Is program executing?
    _program_counter: int = 0  # Current line number (0-based)
    _program_labels: dict = None  # Label name -> line number mapping
    _parsed_program: list = None  # Parsed commands from robobrain
    _blocked_until: float = 0.0  # Game seconds when WAIT/movement finishes
    _message_inbox: list = None  # Received messages [(type, message, timestamp), ...]
    
    def __post_init__(self):
        """Initialize default values for list/dict fields after dataclass construction.
        
        Ensures commands_text, program state, and message inbox are properly initialized.
        Called automatically after __init__ by dataclass.
        """
        if self.commands_text is None:
            self.commands_text = [''] * 10
        if self._program_labels is None:
            self._program_labels = {}
        if self._parsed_program is None:
            self._parsed_program = []
        if self._message_inbox is None:
            self._message_inbox = []

    def move_to(self, target: Position):
        """Move robot to target position instantly.
        
        Args:
            target: (x, y) coordinates to move to
        
        Note:
            Actual pathfinding and timed movement is handled by Map class.
            This method just updates the position field.
        """
        self.pos = target

    def start_loading(self, source, amount: int = None):
        """Initiate loading operation from source object.
        
        Transfer executes at 1 material/second via Map.tick_transfer().
        Cancels any ongoing unloading operation.
        
        Args:
            source: Object to load from (Mine, Storage, Base, or Robot)
            amount: Target materials to load (None = load until full)
        
        Note:
            Sets _loading_from and _loading_amount for tick_transfer() to process.
            Actual transfer logic is in Map.tick_transfer().
        """
        # Initialize fields if missing
        if not hasattr(self, '_loading_from'):
            self._loading_from = None
        if not hasattr(self, '_loading_amount'):
            self._loading_amount = None
        if not hasattr(self, '_unloading_to'):
            self._unloading_to = None
        if not hasattr(self, '_unloading_amount'):
            self._unloading_amount = None
        if not hasattr(self, '_last_transfer_time'):
            self._last_transfer_time = 0.0
            
        # Cancel any ongoing operations
        self._unloading_to = None
        self._unloading_amount = None
        
        # Start loading
        free = self.capacity - self.inventory
        self._loading_from = source
        self._loading_amount = amount if amount is not None else free
        
    def start_unloading(self, target, amount: int = None):
        """Initiate unloading operation to target object.
        
        Transfer executes at 1 material/second via Map.tick_transfer().
        Cancels any ongoing loading operation.
        
        Args:
            target: Object to unload to (Storage, Base, or Robot)
            amount: Target materials to unload (None = unload all inventory)
        
        Note:
            Sets _unloading_to and _unloading_amount for tick_transfer() to process.
            Actual transfer logic is in Map.tick_transfer().
        """
        # Initialize fields if missing
        if not hasattr(self, '_loading_from'):
            self._loading_from = None
        if not hasattr(self, '_loading_amount'):
            self._loading_amount = None
        if not hasattr(self, '_unloading_to'):
            self._unloading_to = None
        if not hasattr(self, '_unloading_amount'):
            self._unloading_amount = None
        if not hasattr(self, '_last_transfer_time'):
            self._last_transfer_time = 0.0
            
        # Cancel any ongoing operations
        self._loading_from = None
        self._loading_amount = None
        
        # Start unloading
        self._unloading_to = target
        self._unloading_amount = amount if amount is not None else self.inventory
    
    def load_from(self, source, amount: int = None) -> int:
        """Instant load operation (legacy method, prefer start_loading for timed transfer).
        
        Args:
            source: Object to load from
            amount: Materials to load (None = fill to capacity)
            
        Returns:
            Number of materials actually loaded
            
        Note:
            This is instant transfer. Use start_loading() for realistic 1/second rate.
        """
        free = self.capacity - self.inventory
        if free <= 0:
            return 0
        
        load_amount = amount if amount is not None else free
        load_amount = min(load_amount, free)
        
        # Withdraw from source
        if hasattr(source, 'withdraw'):
            taken = source.withdraw(load_amount)
        elif isinstance(source, Robot):
            # Take from another robot's inventory
            taken = min(load_amount, source.inventory)
            source.inventory -= taken
        else:
            return 0
        
        self.inventory += taken
        return taken
    
    def unload_to(self, target, amount: int = None) -> int:
        """Unload material to target object (Storage, Base, or Robot)."""
        if self.inventory <= 0:
            return 0
        
        unload_amount = amount if amount is not None else self.inventory
        unload_amount = min(unload_amount, self.inventory)
        
        # Deposit to target
        if hasattr(target, 'store'):
            # Storage
            stored = target.store(unload_amount)
        elif hasattr(target, 'deposit'):
            # Base
            stored = target.deposit(unload_amount)
        elif isinstance(target, Robot):
            # Transfer to another robot
            free = target.capacity - target.inventory
            stored = min(unload_amount, free)
            target.inventory += stored
        else:
            return 0
        
        self.inventory -= stored
        return stored

    def mine(self, mine: Mine, amount: int = None) -> int:
        if self.pos != mine.pos:
            return 0
        free = self.capacity - self.inventory
        if free <= 0:
            return 0
        want = free if amount is None else min(free, amount)
        taken = mine.extract(want)
        self.inventory += taken
        return taken

    def deposit_to_storage(self, storage: Storage) -> int:
        if self.pos != storage.pos:
            return 0
        deposited = storage.store(self.inventory)
        self.inventory -= deposited
        return deposited

    def deposit_to_base(self, base: Base) -> int:
        if self.pos != base.pos:
            return 0
        amount = self.inventory
        accepted = base.deposit(amount)
        self.inventory -= accepted
        return accepted


@dataclass
class Rock(Building):
    """Impassable terrain obstacle.
    
    Blocks robot movement and pathfinding.
    Used for terrain generation and map obstacles.
    """
    pass


def create_object(obj_type: str, id: Optional[int] = None, name: str = None, **kwargs):
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
        return Robot(id=id, pos=kwargs.get('pos', (0, 0)), capacity=kwargs.get('capacity', 5))
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
