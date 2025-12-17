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

    def extract(self, amount: int) -> int:
        if self.durability <= 0:
            return 0
        taken = min(amount, self.durability)
        self.durability -= taken
        return taken


@dataclass
class Storage(Building):
    capacity: int = 100
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

    def deposit(self, amount: int) -> int:
        self.bank += amount
        return amount


@dataclass
class Robot:
    id: Optional[int] = None
    pos: Position = (0, 0)
    capacity: int = 10
    inventory: int = 0

    def move_to(self, target: Position):
        self.pos = target

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
        return Robot(id=id, pos=kwargs.get('pos', (0, 0)), capacity=kwargs.get('capacity', 10))
    if t == 'mine':
        return Mine(id=id, name=name or 'Mine', pos=kwargs.get('pos', (0, 0)), durability=kwargs.get('durability', 10))
    if t == 'storage':
        return Storage(id=id, name=name or 'Storage', pos=kwargs.get('pos', (0, 0)), capacity=kwargs.get('capacity', 100))
    if t == 'base':
        return Base(id=id, name=name or 'Base', pos=kwargs.get('pos', (0, 0)))
    if t == 'rock':
        return Rock(id=id, name=name or 'Rock', pos=kwargs.get('pos', (0, 0)))
    raise ValueError('Unknown object type')
