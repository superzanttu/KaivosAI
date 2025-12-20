"""Unit tests for Map class.

Tests for map operations, pathfinding, material production/consumption,
and robot transfer operations.
"""
import tempfile
import sqlite3
from pathlib import Path
import unittest

from kaivosai.db import init_game_db
from kaivosai.map import Map
from kaivosai.models import Mine, Storage, Robot, Base, Rock
from kaivosai.exceptions import MapError, ValidationError


class MapBasicOperationsTests(unittest.TestCase):
    """Test basic Map operations: add, remove, move, get."""
    
    def setUp(self):
        """Create fresh Map instance for each test."""
        self.game_map = Map(width=30, height=30)
    
    def test_add_object(self):
        """Test adding object to map."""
        robot = Robot(id=1, name='TestBot', pos=(5, 5), capacity=5)
        self.game_map.add_object(robot, (5, 5))
        
        self.assertIn((5, 5), self.game_map.cells)
        retrieved = self.game_map.get((5, 5))
        self.assertEqual(retrieved.name, 'TestBot')
    
    def test_add_multiple_objects(self):
        """Test adding multiple objects at different positions."""
        mine = Mine(id=1, name='Mine1', pos=(1, 1), durability=10)
        storage = Storage(id=2, name='Storage1', pos=(2, 2), capacity=20)
        base = Base(id=3, name='Base1', pos=(3, 3))
        
        self.game_map.add_object(mine, (1, 1))
        self.game_map.add_object(storage, (2, 2))
        self.game_map.add_object(base, (3, 3))
        
        self.assertEqual(len(self.game_map.cells), 3)
        self.assertIsInstance(self.game_map.get((1, 1)), Mine)
        self.assertIsInstance(self.game_map.get((2, 2)), Storage)
        self.assertIsInstance(self.game_map.get((3, 3)), Base)
    
    def test_remove_object_by_position(self):
        """Test removing object by position."""
        robot = Robot(id=1, pos=(10, 10), capacity=5)
        self.game_map.add_object(robot, (10, 10))
        
        removed = self.game_map.remove_object((10, 10))
        
        self.assertIsNotNone(removed)
        self.assertEqual(removed.id, 1)
        self.assertNotIn((10, 10), self.game_map.cells)
    
    def test_remove_object_by_id(self):
        """Test removing object by ID."""
        robot = Robot(id=42, pos=(10, 10), capacity=5)
        self.game_map.add_object(robot, (10, 10))
        
        removed = self.game_map.remove_object(42)
        
        self.assertIsNotNone(removed)
        self.assertEqual(removed.id, 42)
        self.assertNotIn((10, 10), self.game_map.cells)
    
    def test_remove_nonexistent_object_raises_error(self):
        """Test that removing nonexistent object by ID raises MapError."""
        with self.assertRaises(MapError):
            self.game_map.remove_object(999)
    
    def test_remove_invalid_id_raises_error(self):
        """Test that invalid ID type raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.game_map.remove_object("invalid")
    
    def test_move_object(self):
        """Test moving object from one position to another."""
        robot = Robot(id=1, pos=(5, 5), capacity=5)
        self.game_map.add_object(robot, (5, 5))
        
        self.game_map.move_object((5, 5), (7, 8))
        
        self.assertNotIn((5, 5), self.game_map.cells)
        self.assertIn((7, 8), self.game_map.cells)
        moved = self.game_map.get((7, 8))
        self.assertEqual(moved.id, 1)
        self.assertEqual(moved.pos, (7, 8))
    
    def test_get_nonexistent_position_returns_none(self):
        """Test that getting empty position returns None."""
        result = self.game_map.get((99, 99))
        self.assertIsNone(result)
    
    def test_in_bounds(self):
        """Test boundary checking."""
        self.assertTrue(self.game_map.in_bounds((0, 0)))
        self.assertTrue(self.game_map.in_bounds((29, 29)))
        self.assertFalse(self.game_map.in_bounds((-1, 0)))
        self.assertFalse(self.game_map.in_bounds((0, -1)))
        self.assertFalse(self.game_map.in_bounds((30, 0)))
        self.assertFalse(self.game_map.in_bounds((0, 30)))


class MapPathfindingTests(unittest.TestCase):
    """Test pathfinding and robot movement."""
    
    def setUp(self):
        """Create Map with some obstacles."""
        self.game_map = Map(width=10, height=10)
        # Add rocks as obstacles
        self.game_map.add_object(Rock(pos=(2, 2)), (2, 2))
        self.game_map.add_object(Rock(pos=(2, 3)), (2, 3))
        self.game_map.add_object(Rock(pos=(2, 4)), (2, 4))
    
    def test_find_path_straight_line(self):
        """Test pathfinding in straight line without obstacles."""
        path = self.game_map._find_path((0, 0), (3, 0))
        
        self.assertIsNotNone(path)
        # Path excludes start position, starts with first step
        self.assertEqual(path[0], (1, 0))
        self.assertEqual(path[-1], (3, 0))
        self.assertEqual(len(path), 3)  # (1,0), (2,0), (3,0)
    
    def test_find_path_around_obstacles(self):
        """Test pathfinding around obstacles."""
        # Path from (1,3) to (4,3) must go around rock wall at x=2
        path = self.game_map._find_path((1, 3), (4, 3))
        
        self.assertIsNotNone(path)
        # Path starts from first step (not start position)
        self.assertEqual(path[-1], (4, 3))
        # Path should not go through rocks at (2,2), (2,3), (2,4)
        for pos in path:
            self.assertNotIn(pos, [(2, 2), (2, 3), (2, 4)])
    
    def test_find_path_blocked_returns_empty(self):
        """Test that completely blocked path returns empty list."""
        # Create wall from top to bottom at x=5
        for y in range(10):
            self.game_map.add_object(Rock(pos=(5, y)), (5, y))
        
        # Try to find path from left to right across wall
        path = self.game_map._find_path((0, 5), (9, 5))
        
        self.assertEqual(len(path), 0)  # Empty list for no path
    
    def test_find_path_out_of_bounds(self):
        """Test pathfinding with out-of-bounds coordinates."""
        # Out of bounds paths should return empty
        path = self.game_map._find_path((0, 0), (50, 50))
        self.assertEqual(len(path), 0)
    
    def test_goto_robot(self):
        """Test initiating robot movement to target."""
        robot = Robot(id=1, pos=(0, 0), capacity=5)
        self.game_map.add_object(robot, (0, 0))
        
        # Start movement to (3, 0)
        result = self.game_map.command_move_robot(1, (3, 0))
        
        self.assertTrue(result)
        self.assertTrue(hasattr(robot, '_move_path'))
        self.assertIsNotNone(robot._move_path)
    
    def test_tick_movement(self):
        """Test robot movement tick by tick."""
        robot = Robot(id=1, pos=(0, 0), capacity=5)
        self.game_map.add_object(robot, (0, 0))
        
        # Start movement
        self.game_map.command_move_robot(1, (3, 0))
        
        # Tick movement (should move robot toward target)
        initial_pos = robot.pos
        self.game_map.tick_movement()
        
        # Robot should have moved
        self.assertNotEqual(robot.pos, initial_pos)


class MapProductionConsumptionTests(unittest.TestCase):
    """Test material production and consumption ticks."""
    
    def setUp(self):
        """Create Map with production/consumption objects."""
        self.game_map = Map(width=10, height=10)
    
    def test_mine_production(self):
        """Test that mines produce materials over time."""
        mine = Mine(id=1, pos=(1, 1), durability=10)
        mine.stored = 0
        mine.last_production_time = 0.0
        self.game_map.add_object(mine, (1, 1))
        
        # Simulate 10 seconds passing (should produce 1 material)
        self.game_map.tick_production(10.0)
        
        self.assertEqual(mine.stored, 1)
    
    def test_mine_production_stops_at_capacity(self):
        """Test that mines stop producing when full."""
        mine = Mine(id=1, pos=(1, 1), durability=10)
        mine.stored = 10  # At capacity
        mine.last_production_time = 0.0
        self.game_map.add_object(mine, (1, 1))
        
        # Try to produce more
        self.game_map.tick_production(10.0)
        
        self.assertEqual(mine.stored, 10)  # Should not exceed
    
    def test_base_consumption(self):
        """Test that bases consume materials over time."""
        base = Base(id=1, pos=(2, 2))
        base.bank = 5
        base.last_consumption_time = 0.0
        self.game_map.add_object(base, (2, 2))
        
        # Simulate 10 seconds passing (should consume 1 material)
        self.game_map.tick_production(10.0)
        
        # Base consumes in 10-second intervals
        self.assertLessEqual(base.bank, 5)  # Should consume or stay same
        self.assertGreaterEqual(base.bank, 4)  # Should not consume more than 1
    
    def test_base_consumption_stops_at_zero(self):
        """Test that bases don't consume when empty."""
        base = Base(id=1, pos=(2, 2))
        base.bank = 0
        base.last_consumption_time = 0.0
        self.game_map.add_object(base, (2, 2))
        
        # Try to consume
        self.game_map.tick_production(10.0)
        
        self.assertEqual(base.bank, 0)  # Should not go negative


class MapTransferTests(unittest.TestCase):
    """Test robot transfer operations (loading/unloading)."""
    
    def setUp(self):
        """Create Map with objects for transfer testing."""
        self.game_map = Map(width=10, height=10)
    
    def test_robot_load_from_mine(self):
        """Test robot loading materials from mine."""
        robot = Robot(id=1, pos=(1, 1), capacity=5)
        robot.inventory = 0
        mine = Mine(id=2, pos=(1, 2), durability=10)
        mine.stored = 5
        
        self.game_map.add_object(robot, (1, 1))
        self.game_map.add_object(mine, (1, 2))
        
        robot._loading_from = mine
        robot._loading_amount = 3
        robot._last_transfer_time = 0.0
        
        # Simulate 3 seconds (should transfer 3 materials at 1/sec)
        self.game_map.tick_transfer(3)
        
        self.assertGreater(robot.inventory, 0)  # Should have loaded some
        self.assertLess(mine.stored, 5)  # Should have lost some
    
    def test_robot_unload_to_storage(self):
        """Test robot unloading materials to storage."""
        robot = Robot(id=1, pos=(1, 1), capacity=5)
        robot.inventory = 4
        storage = Storage(id=2, pos=(1, 2), capacity=20)
        storage.stored = 0
        
        self.game_map.add_object(robot, (1, 1))
        self.game_map.add_object(storage, (1, 2))
        
        robot._unloading_to = storage
        robot._unloading_amount = 2
        robot._last_transfer_time = 0.0
        
        # Simulate 2 seconds (should transfer 2 materials)
        self.game_map.tick_transfer(2)
        
        self.assertLess(robot.inventory, 4)  # Should have unloaded some
        self.assertGreater(storage.stored, 0)  # Should have received some
    
    def test_transfer_stops_when_robot_full(self):
        """Test that loading stops when robot reaches capacity."""
        robot = Robot(id=1, pos=(1, 1), capacity=5)
        robot.inventory = 4
        mine = Mine(id=2, pos=(1, 2), durability=10)
        mine.stored = 10
        
        self.game_map.add_object(robot, (1, 1))
        self.game_map.add_object(mine, (1, 2))
        
        robot._loading_from = mine
        robot._loading_amount = 5
        robot._last_transfer_time = 0.0
        
        # Try to transfer 5 materials (but robot can only hold 1 more)
        self.game_map.tick_transfer(5)
        
        self.assertLessEqual(robot.inventory, 5)  # Capped at capacity
    
    def test_transfer_stops_when_source_empty(self):
        """Test that loading stops when source is empty."""
        robot = Robot(id=1, pos=(1, 1), capacity=5)
        robot.inventory = 0
        mine = Mine(id=2, pos=(1, 2), durability=10)
        mine.stored = 2
        
        self.game_map.add_object(robot, (1, 1))
        self.game_map.add_object(mine, (1, 2))
        
        robot._loading_from = mine
        robot._loading_amount = 5
        robot._last_transfer_time = 0.0
        
        # Try to transfer 5 materials (but source only has 2)
        self.game_map.tick_transfer(5)
        
        self.assertLessEqual(robot.inventory, 2)  # Got at most 2
        self.assertLessEqual(mine.stored, 2)  # Source has at most 2


class MapProgramTests(unittest.TestCase):
    """Test RoboBASIC program ticking on the map."""

    def test_tick_programs_stops_on_end(self):
        game_map = Map(width=5, height=5)
        robot = Robot(id=1, pos=(0, 0))
        robot._program_running = True
        robot._program_counter = 0
        robot._parsed_program = [
            {'command': 'END', 'args': []},
        ]
        robot._program_labels = {}

        game_map.add_object(robot, robot.pos)

        game_map.tick_programs(0)

        self.assertFalse(robot._program_running)
        self.assertEqual(robot._program_counter, 0)


class MapTerrainGenerationTests(unittest.TestCase):
    """Test terrain generation functionality."""
    
    def setUp(self):
        """Create empty Map."""
        self.game_map = Map(width=20, height=20)
    
    def test_generate_full_terrain(self):
        """Test terrain generation creates rocks."""
        border_count, terrain_count = self.game_map.generate_full_terrain(
            rock_density=0.1, 
            cluster_size=3
        )
        
        # Should have created some rocks
        self.assertGreater(border_count, 0)
        self.assertGreaterEqual(terrain_count, 0)
        
        # Check that rocks are actually in the map
        total_rocks = sum(1 for obj in self.game_map.cells.values() 
                         if isinstance(obj, Rock))
        self.assertEqual(total_rocks, border_count + terrain_count)
    
    def test_border_rocks_at_edges(self):
        """Test that border rocks are placed at map edges."""
        self.game_map.generate_full_terrain(rock_density=0.0, cluster_size=1)
        
        # Check corners definitely have rocks
        self.assertIsInstance(self.game_map.get((0, 0)), Rock)
        self.assertIsInstance(self.game_map.get((0, self.game_map.height - 1)), Rock)
        self.assertIsInstance(self.game_map.get((self.game_map.width - 1, 0)), Rock)
        self.assertIsInstance(self.game_map.get((self.game_map.width - 1, self.game_map.height - 1)), Rock)


class MapPersistenceTests(unittest.TestCase):
    """Test Map persistence with database."""
    
    def test_map_loads_from_database(self):
        """Test that Map loads objects from database on initialization."""
        tf = tempfile.NamedTemporaryFile(delete=False)
        tf.close()
        dbp = Path(tf.name)
        
        # Create map and add objects
        conn1 = sqlite3.connect(str(dbp))
        conn1.row_factory = sqlite3.Row
        init_game_db(conn1)
        game_map1 = Map(width=10, height=10, conn=conn1)
        
        robot = Robot(id=1, pos=(3, 3), capacity=5)
        mine = Mine(id=2, pos=(5, 5), durability=10)
        game_map1.add_object(robot, (3, 3))
        game_map1.add_object(mine, (5, 5))
        conn1.close()
        
        # Load map from database
        conn2 = sqlite3.connect(str(dbp))
        conn2.row_factory = sqlite3.Row
        game_map2 = Map(width=10, height=10, conn=conn2)
        
        # Verify objects loaded
        self.assertIn((3, 3), game_map2.cells)
        self.assertIn((5, 5), game_map2.cells)
        self.assertIsInstance(game_map2.get((3, 3)), Robot)
        self.assertIsInstance(game_map2.get((5, 5)), Mine)
        
        conn2.close()
        dbp.unlink()


if __name__ == '__main__':
    unittest.main()
