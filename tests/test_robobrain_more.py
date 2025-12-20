import unittest
from kaivosai.robobrain import RoboBRAINExecutor
from kaivosai.models import Robot, Mine, Storage, Base
from kaivosai.map import Map


class RoboBrainMoreTests(unittest.TestCase):
    def test_unknown_command_returns_message(self):
        robot = Robot(id=1, pos=(0, 0))
        game_map = Map(width=3, height=3)
        robot._program_running = True
        robot._program_counter = 0
        robot._parsed_program = [
            {'command': 'FOO', 'args': []},
        ]
        result = RoboBRAINExecutor.execute_next_line(robot, game_map, 0)
        self.assertIn('Unknown command', result)
        self.assertEqual(robot._program_counter, 1)

    def test_if_dst_true_and_src_true(self):
        robot = Robot(id=1, pos=(1, 1))
        game_map = Map(width=4, height=4)
        storage = Storage(pos=(1, 2), capacity=10, stored=5)
        mine = Mine(pos=(2, 1), stored=3, capacity=10)
        game_map.add_object(robot, robot.pos)
        game_map.add_object(storage, storage.pos)
        game_map.add_object(mine, mine.pos)

        # DST: storage not full
        robot._program_running = True
        robot._program_counter = 0
        robot._program_labels = {'J': 2}
        robot._parsed_program = [
            {'command': 'IF', 'args': [False, 'NEAR', '1', 'DST', ':J']},
        ]
        result1 = RoboBRAINExecutor.execute_next_line(robot, game_map, 0)
        self.assertIsNone(result1)
        self.assertEqual(robot._program_counter, 1)

        # SRC: mine has stored > 0
        robot._program_counter = 0
        robot._parsed_program = [
            {'command': 'IF', 'args': [False, 'NEAR', '1', 'SRC', ':J']},
        ]
        result2 = RoboBRAINExecutor.execute_next_line(robot, game_map, 0)
        self.assertIsNone(result2)
        self.assertEqual(robot._program_counter, 1)

    def test_execute_load_and_unload_skip_on_multiple(self):
        robot = Robot(id=1, pos=(1, 1))
        game_map = Map(width=4, height=4)
        s1 = Storage(pos=(1, 2), capacity=10, stored=1)
        s2 = Storage(pos=(2, 1), capacity=10, stored=2)
        game_map.add_object(robot, robot.pos)
        game_map.add_object(s1, s1.pos)
        game_map.add_object(s2, s2.pos)

        robot._program_running = True
        robot._program_counter = 0
        robot._parsed_program = [
            {'command': 'LOAD', 'args': []},
        ]
        # Multiple sources -> skip
        res_load = RoboBRAINExecutor.execute_next_line(robot, game_map, 0)
        self.assertIsNone(res_load)
        self.assertEqual(robot._program_counter, 1)

        # Multiple dest -> skip
        robot._program_counter = 0
        robot._parsed_program = [
            {'command': 'UNLOAD', 'args': []},
        ]
        res_unload = RoboBRAINExecutor.execute_next_line(robot, game_map, 0)
        self.assertIsNone(res_unload)
        self.assertEqual(robot._program_counter, 1)

    def test_goto_invalid_target(self):
        robot = Robot(id=1, pos=(0, 0))
        game_map = Map(width=3, height=3)
        robot._program_running = True
        robot._program_counter = 0
        robot._parsed_program = [
            {'command': 'GOTO', 'args': [('invalid',)]},
        ]
        result = RoboBRAINExecutor.execute_next_line(robot, game_map, 0)
        self.assertIn('Invalid target', result)
        self.assertEqual(robot._program_counter, 1)


if __name__ == '__main__':
    unittest.main()
