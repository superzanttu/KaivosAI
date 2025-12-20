from dataclasses import dataclass
from typing import Tuple, Optional

Position = Tuple[int, int]


@dataclass
class Building:
    id: Optional[int] = None
    name: str = ""
    pos: Position = (0, 0)


@dataclass
class Mine(Building):
    ore_type: str = "ore"
    durability: int = 10
    stored: int = 0
    capacity: int = 10
    last_production_time: float = 0.0

    def extract(self, amount: int) -> int:
        if self.durability <= 0:
            return 0
        taken = min(amount, self.durability)
        self.durability -= taken
        return taken
    
    def produce(self, game_seconds: int) -> int:
        """Produce material every 10 seconds if not full."""
        # Initialize fields if missing (for objects loaded from old DB)
        if not hasattr(self, 'stored') or self.stored is None:
            self.stored = 0
        if not hasattr(self, 'capacity') or self.capacity is None:
            self.capacity = 10
        if not hasattr(self, 'last_production_time'):
            self.last_production_time = 0.0
            
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
        """Withdraw material from mine storage."""
        take = min(self.stored, amount)
        self.stored -= take
        return take


@dataclass
class Storage(Building):
    capacity: int = 20
    stored: int = 0

    def store(self, amount: int) -> int:
        space = self.capacity - self.stored
        if space <= 0:
            return 0
        put = min(space, amount)
        self.stored += put
        return put

    def withdraw(self, amount: int) -> int:
        take = min(self.stored, amount)
        self.stored -= take
        return take


@dataclass
class Base(Building):
    bank: int = 0
    stored: int = 0
    last_consumption_time: float = 0.0

    def deposit(self, amount: int) -> int:
        self.bank += amount
        self.stored += amount
        return amount
    
    def consume(self, game_seconds: int) -> int:
        """Consume 1 material every 10 seconds if material available."""
        # Initialize fields if missing (for objects loaded from old DB)
        if not hasattr(self, 'stored') or self.stored is None:
            self.stored = 0
        if not hasattr(self, 'last_consumption_time'):
            self.last_consumption_time = 0.0
            
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
    id: Optional[int] = None
    pos: Position = (0, 0)
    capacity: int = 5
    inventory: int = 0
    name: str = "Robot"

    def move_to(self, target: Position):
        self.pos = target

    def load_from(self, source, amount: int = None) -> int:
        """Load material from source object (Mine, Storage, Base, or Robot)."""
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
    pass


def create_object(obj_type: str, id: Optional[int] = None, name: str = None, **kwargs):
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
