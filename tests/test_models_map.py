import random
import unittest

from kaivosai.exceptions import MapError, ValidationError
from kaivosai.map import Map
from kaivosai.models import Base, Mine, Robot, Rock, Storage


class ModelBehaviorTests(unittest.TestCase):
    def test_mine_production_respects_interval_and_capacity(self):
        mine = Mine(stored=0, capacity=2)
        self.assertEqual(mine.produce(0), 0)
        self.assertEqual(mine.stored, 0)

        # Produces once 10 seconds have elapsed
        self.assertEqual(mine.produce(9), 0)
        self.assertEqual(mine.produce(10), 1)
        self.assertEqual(mine.stored, 1)

        # Produces again after the next interval, then stops at capacity
        self.assertEqual(mine.produce(19), 0)
        self.assertEqual(mine.produce(20), 1)
        self.assertEqual(mine.stored, 2)
        self.assertEqual(mine.produce(30), 0)
        self.assertEqual(mine.stored, 2)

    def test_base_deposit_and_consume_cycle(self):
        base = Base(stored=0, bank=0)
        base.deposit(3)
        self.assertEqual(base.bank, 3)
        self.assertEqual(base.stored, 3)

        # First consumption after 10s
        self.assertEqual(base.consume(0), 0)
        self.assertEqual(base.consume(10), 1)
        # No consumption before next interval
        self.assertEqual(base.consume(15), 0)
        self.assertEqual(base.consume(20), 1)
        self.assertEqual(base.stored, 1)

    def test_storage_store_and_withdraw(self):
        storage = Storage(capacity=5, stored=0)
        self.assertEqual(storage.store(10), 5)
        self.assertEqual(storage.stored, 5)
        self.assertEqual(storage.withdraw(3), 3)
        self.assertEqual(storage.stored, 2)

    def test_robot_defaults_initialized(self):
        robot = Robot()
        self.assertEqual(len(robot.commands_text), 10)
        self.assertFalse(robot._program_running)
        self.assertEqual(robot._program_counter, 0)
        self.assertEqual(robot._message_inbox, [])


class MapBehaviorTests(unittest.TestCase):
    def test_generate_full_terrain_adds_border_and_interiors(self):
        random.seed(0)
        game_map = Map(width=6, height=5)

        border, terrain = game_map.generate_full_terrain(rock_density=1.0, cluster_size=1)

        # Border: top+bottom (6+6) + sides without corners (3*2) = 18
        self.assertEqual(border, 18)
        self.assertGreaterEqual(terrain, 1)
        for pos in [(0, 0), (5, 0), (0, 4), (5, 4)]:
            self.assertIsInstance(game_map.get(pos), Rock)

    def test_command_move_robot_honors_stop_distance(self):
        game_map = Map(width=5, height=5)
        robot = Robot(id=1, pos=(1, 1))
        game_map.add_object(robot, robot.pos)

        started = game_map.command_move_robot(1, (3, 1), stop_distance=1)
        self.assertTrue(started)
        self.assertEqual(robot._move_target, (3, 1))
        self.assertEqual(robot._move_path, [(2, 1)])

        # Advance one step; robot should stop one cell short of target
        game_map.tick_movement()
        self.assertEqual(game_map.get((2, 1)), robot)
        self.assertEqual(robot._move_path, [])

    def test_command_move_robot_rejects_out_of_bounds(self):
        game_map = Map(width=4, height=4)
        robot = Robot(id=1, pos=(0, 0))
        game_map.add_object(robot, robot.pos)

        with self.assertRaises(ValueError):
            game_map.command_move_robot(1, (10, 10))

    def test_move_object_validation_errors(self):
        game_map = Map(width=3, height=3)
        robot = Robot(pos=(1, 1))
        game_map.add_object(robot, robot.pos)

        with self.assertRaises(ValueError):
            game_map.move_object((1, 1), (3, 3))
        with self.assertRaises(ValueError):
            game_map.move_object((1, 1), (1, 1))

    def test_remove_object_validation_and_missing(self):
        game_map = Map(width=3, height=3)
        with self.assertRaises(ValidationError):
            game_map.remove_object("not-a-number")
        with self.assertRaises(MapError):
            game_map.remove_object(99)


if __name__ == "__main__":
    unittest.main()
