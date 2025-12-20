"""Unit tests for RoboBRAIN parser and executor."""

import unittest
from unittest.mock import Mock, MagicMock, patch
from kaivosai.robobrain import RoboBASICParser, RoboBRAINExecutor, SyntaxError as RoboSyntaxError
from kaivosai.models import Robot, Mine, Storage, Base
from kaivosai.map import Map


class TestRoboBASICParser(unittest.TestCase):
    """Test RoboBASIC syntax parser and validator."""
    
    def test_empty_program(self):
        """Test parsing empty program."""
        lines = [''] * 10
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(labels), 0)
    
    def test_line_too_long(self):
        """Test that lines over 20 chars are rejected."""
        lines = ['GOTO 1 2 3 4 5 6 7 8 9'] + [''] * 9
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertGreater(len(errors), 0)
        self.assertIn('Line 1', errors[0])
        self.assertIn('20 chars', errors[0])
    
    def test_label_definition(self):
        """Test label definition parsing."""
        lines = [':START', 'U 5', ':LOOP', 'WAIT 10', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertIn('START', labels)
        self.assertIn('LOOP', labels)
        self.assertEqual(labels['START'], 1)
        self.assertEqual(labels['LOOP'], 3)
    
    def test_label_too_long(self):
        """Test that labels over 10 chars are rejected."""
        lines = [':VERYLONGLABEL', ''] * 9
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertGreater(len(errors), 0)
        self.assertIn('Label', errors[0])
    
    def test_duplicate_labels(self):
        """Test that duplicate labels are rejected."""
        lines = [':START', 'U 5', ':START', 'D 3', ''] * 2 + [''] * 2
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertGreater(len(errors), 0)
        self.assertIn('Duplicate', errors[0])
    
    def test_undefined_label_reference(self):
        """Test that undefined label references are caught."""
        lines = ['GOTO :NOWHERE', ''] * 9
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertGreater(len(errors), 0)
        self.assertIn('Undefined', errors[0])
        self.assertIn('NOWHERE', errors[0])
    
    def test_goto_coords(self):
        """Test GOTO with coordinates."""
        lines = ['GOTO 15 20', ''] * 9
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['command'], 'GOTO')
        self.assertEqual(parsed[0]['args'][0][0], 'coords')
        self.assertEqual(parsed[0]['args'][0][1], 15)
        self.assertEqual(parsed[0]['args'][0][2], 20)
    
    def test_goto_object(self):
        """Test GOTO with object ID."""
        lines = ['GOTO 42 d 2', ''] * 9
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['command'], 'GOTO')
        self.assertEqual(parsed[0]['args'][0][0], 'object')
        self.assertEqual(parsed[0]['args'][0][1], 42)
        self.assertEqual(parsed[0]['args'][0][2], 2)
    
    def test_directional_movement(self):
        """Test U/D/L/R commands."""
        lines = ['U 5', 'D 3', 'L 10', 'R 2', ''] * 2 + [''] * 2
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['command'], 'U')
        self.assertEqual(parsed[0]['args'][0], 5)
        self.assertEqual(parsed[1]['command'], 'D')
        self.assertEqual(parsed[2]['command'], 'L')
        self.assertEqual(parsed[3]['command'], 'R')
    
    def test_load_unload(self):
        """Test LOAD and UNLOAD commands."""
        lines = ['LOAD', 'LOAD 5', 'UNLOAD', 'UNLOAD 3', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['command'], 'LOAD')
        self.assertEqual(len(parsed[0]['args']), 0)  # No args
        self.assertEqual(parsed[1]['command'], 'LOAD')
        self.assertEqual(parsed[1]['args'][0], 5)
        self.assertEqual(parsed[2]['command'], 'UNLOAD')
    
    def test_if_full_empty(self):
        """Test IF FULL and IF EMPTY conditions."""
        lines = ['IF FULL :LABEL1', 'IF EMPTY :LABEL2', ':LABEL1', ':LABEL2', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['command'], 'IF')
        self.assertFalse(parsed[0]['args'][0])  # not negated
        self.assertEqual(parsed[0]['args'][1], 'FULL')
        self.assertEqual(parsed[1]['args'][1], 'EMPTY')
    
    def test_if_not(self):
        """Test IF NOT conditions."""
        lines = ['IF NOT FULL :GO', ':GO', '', '', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertTrue(parsed[0]['args'][0])  # negated
        self.assertEqual(parsed[0]['args'][1], 'FULL')
    
    def test_if_near(self):
        """Test IF NEAR condition."""
        lines = ['IF NEAR 0 SRC :LBL', 'IF NEAR 1 MINE :L', 'IF NEAR MANY ANY :X', ':LBL', ':L', ':X', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['args'][1], 'NEAR')
        self.assertEqual(parsed[0]['args'][2], '0')
        self.assertEqual(parsed[0]['args'][3], 'SRC')
    
    def test_if_scan(self):
        """Test IF SCAN directional condition."""
        lines = ['IF U 5 MINE :UP', 'IF D 3 SRC :DOWN', ':UP', ':DOWN', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['args'][1], 'SCAN')
        self.assertEqual(parsed[0]['args'][2], 'U')
        self.assertEqual(parsed[0]['args'][3], 5)
        self.assertEqual(parsed[0]['args'][4], 'MINE')
    
    def test_if_range(self):
        """Test IF RANGE area condition."""
        lines = ['IF RANGE 5 ANY :GO', ':GO', '', '', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['args'][1], 'RANGE')
        self.assertEqual(parsed[0]['args'][2], 5)
        self.assertEqual(parsed[0]['args'][3], 'ANY')
    
    def test_if_msg(self):
        """Test IF MSG message condition."""
        lines = ['IF MSG ROBOTS HI :L', ':L', '', '', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['args'][1], 'MSG')
        self.assertEqual(parsed[0]['args'][2], 'ROBOTS')
        self.assertEqual(parsed[0]['args'][3], 'HI')
    
    def test_send_command(self):
        """Test SEND message command."""
        lines = ['SEND ROBOTS HELLO', 'SEND MINES STATUS', '', '', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['command'], 'SEND')
        self.assertEqual(parsed[0]['args'][0], 'ROBOTS')
        self.assertEqual(parsed[0]['args'][1], 'HELLO')
    
    def test_clear_command(self):
        """Test CLEAR inbox command."""
        lines = ['CLEAR', '', '', '', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['command'], 'CLEAR')
    
    def test_wait_command(self):
        """Test WAIT duration command."""
        lines = ['WAIT 10', 'WAIT 300', '', '', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['command'], 'WAIT')
        self.assertEqual(parsed[0]['args'][0], 10)
        self.assertEqual(parsed[1]['args'][0], 300)
    
    def test_end_command(self):
        """Test END program command."""
        lines = ['END', '', '', '', '', '', '', '', '', '']
        parsed, labels, errors = RoboBASICParser.parse_program(lines)
        self.assertEqual(len(errors), 0)
        self.assertEqual(parsed[0]['command'], 'END')


class TestRoboBRAINExecutor(unittest.TestCase):
    """Test RoboBRAIN program executor."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.robot = Robot(id=1, name='TestBot', pos=(10, 10), capacity=5)
        self.robot._program_running = True
        self.robot._program_counter = 0
        self.robot._blocked_until = 0.0
        self.robot._message_inbox = []
        self.robot.inventory = 0
        
        self.map = Mock(spec=Map)
        self.executor = RoboBRAINExecutor()
    
    def test_execute_empty_line(self):
        """Test execution skips empty lines."""
        self.robot._parsed_program = [
            {'command': None, 'args': []},
            {'command': 'END', 'args': []},
        ]
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(self.robot._program_counter, 1)
    
    def test_execute_end_command(self):
        """Test END command stops program."""
        self.robot._parsed_program = [
            {'command': 'END', 'args': []},
        ]
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIn('ended', result.lower())
        self.assertFalse(self.robot._program_running)
    
    def test_execute_wait_command(self):
        """Test WAIT command blocks robot."""
        self.robot._parsed_program = [
            {'command': 'WAIT', 'args': [10]},
            {'command': 'END', 'args': []},
        ]
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(self.robot._blocked_until, 110)
        self.assertEqual(self.robot._program_counter, 1)
    
    def test_execute_blocked(self):
        """Test blocked robot doesn't execute."""
        self.robot._blocked_until = 200
        self.robot._parsed_program = [{'command': 'END', 'args': []}]
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(self.robot._program_counter, 0)  # unchanged
    
    def test_execute_clear_command(self):
        """Test CLEAR empties inbox."""
        self.robot._message_inbox = [('ROBOT', 'TEST', 100), ('MINE', 'HI', 150)]
        self.robot._parsed_program = [
            {'command': 'CLEAR', 'args': []},
        ]
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(len(self.robot._message_inbox), 0)
        self.assertEqual(self.robot._program_counter, 1)
    
    def test_execute_goto_label(self):
        """Test GOTO label jumps correctly."""
        self.robot._parsed_program = [
            {'command': 'GOTO', 'args': [':SKIP']},
            {'command': 'WAIT', 'args': [99]},
            {'command': 'END', 'args': []},
        ]
        self.robot._program_labels = {'SKIP': 3}
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(self.robot._program_counter, 2)  # 3 - 1
    
    def test_execute_goto_undefined_label(self):
        """Test GOTO to undefined label stops program."""
        self.robot._parsed_program = [
            {'command': 'GOTO', 'args': [':NOWHERE']},
        ]
        self.robot._program_labels = {}
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIn('Undefined', result)
        self.assertFalse(self.robot._program_running)
    
    def test_execute_goto_coords(self):
        """Test GOTO coordinates calls movement."""
        self.robot._parsed_program = [
            {'command': 'GOTO', 'args': [('coords', 15, 20, 0)]},
        ]
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.map.command_move_robot.assert_called_once_with(1, (15, 20), 0)
        self.assertEqual(self.robot._program_counter, 1)
    
    def test_execute_direction_up(self):
        """Test U command calculates target correctly."""
        self.robot.pos = (10, 10)
        self.robot._parsed_program = [
            {'command': 'U', 'args': [5]},
        ]
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.map.command_move_robot.assert_called_once_with(1, (10, 5), 0)
    
    def test_execute_direction_down(self):
        """Test D command calculates target correctly."""
        self.robot.pos = (10, 10)
        self.robot._parsed_program = [
            {'command': 'D', 'args': [3]},
        ]
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.map.command_move_robot.assert_called_once_with(1, (10, 13), 0)
    
    def test_execute_if_full_true(self):
        """Test IF FULL jumps when inventory is full."""
        self.robot.inventory = 5
        self.robot.capacity = 5
        self.robot._parsed_program = [
            {'command': 'IF', 'args': [False, 'FULL', ':FULL']},
            {'command': 'WAIT', 'args': [10]},
        ]
        self.robot._program_labels = {'FULL': 2}
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(self.robot._program_counter, 1)  # jumped to line 2 (2-1=1)
    
    def test_execute_if_full_false(self):
        """Test IF FULL doesn't jump when not full."""
        self.robot.inventory = 3
        self.robot.capacity = 5
        self.robot._parsed_program = [
            {'command': 'IF', 'args': [False, 'FULL', ':FULL']},
            {'command': 'END', 'args': []},
        ]
        self.robot._program_labels = {'FULL': 3}
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(self.robot._program_counter, 1)  # continued to next line
    
    def test_execute_if_not_full(self):
        """Test IF NOT FULL with negation."""
        self.robot.inventory = 3
        self.robot.capacity = 5
        self.robot._parsed_program = [
            {'command': 'IF', 'args': [True, 'FULL', ':NOTFULL']},  # negated
            {'command': 'END', 'args': []},
        ]
        self.robot._program_labels = {'NOTFULL': 2}
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(self.robot._program_counter, 1)  # jumped (NOT FULL = True)
    
    def test_execute_if_empty_true(self):
        """Test IF EMPTY jumps when inventory empty."""
        self.robot.inventory = 0
        self.robot._parsed_program = [
            {'command': 'IF', 'args': [False, 'EMPTY', ':EMPTY']},
            {'command': 'END', 'args': []},
        ]
        self.robot._program_labels = {'EMPTY': 2}
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(self.robot._program_counter, 1)  # jumped
    
    def test_execute_if_near(self):
        """Test IF NEAR checks adjacent objects."""
        mine1 = Mine(id=10, name='Mine1', pos=(10, 11), capacity=10)
        self.map.get_adjacent_objects.return_value = [mine1]
        
        self.robot._parsed_program = [
            {'command': 'IF', 'args': [False, 'NEAR', '1', 'MINE', ':FOUND']},
            {'command': 'END', 'args': []},
        ]
        self.robot._program_labels = {'FOUND': 2}
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(self.robot._program_counter, 1)  # jumped (found 1 mine)
    
    def test_execute_if_msg_found(self):
        """Test IF MSG finds matching message."""
        self.robot._message_inbox = [
            ('ROBOT', 'HELLO', 100),
            ('MINE', 'STATUS', 150),
        ]
        self.robot._parsed_program = [
            {'command': 'IF', 'args': [False, 'MSG', 'ROBOT', 'HELLO', ':GOT']},
        ]
        self.robot._program_labels = {'GOT': 2}
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(self.robot._program_counter, 1)  # jumped
        # Message should be consumed
        self.assertEqual(len(self.robot._message_inbox), 1)
        self.assertEqual(self.robot._message_inbox[0][1], 'STATUS')
    
    def test_execute_if_msg_expired(self):
        """Test IF MSG ignores expired messages."""
        # Message from 4000 seconds ago (> 3600 expiry)
        self.robot._message_inbox = [('ROBOT', 'OLD', 100)]
        self.robot._parsed_program = [
            {'command': 'IF', 'args': [False, 'MSG', 'ROBOT', 'OLD', ':GOT']},
            {'command': 'END', 'args': []},
        ]
        self.robot._program_labels = {'GOT': 2}
        
        result = self.executor.execute_next_line(self.robot, self.map, 5000)
        self.assertIsNone(result)
        self.assertEqual(self.robot._program_counter, 1)  # didn't jump (expired)
    
    def test_execute_load_command(self):
        """Test LOAD starts loading from adjacent source."""
        mine = Mine(id=10, name='Mine1', pos=(10, 11), capacity=10)
        mine.stored = 5
        self.map.get_adjacent_objects.return_value = [mine]
        
        self.robot._parsed_program = [
            {'command': 'LOAD', 'args': [None]},
        ]
        
        with patch.object(self.robot, 'start_loading') as mock_load:
            result = self.executor.execute_next_line(self.robot, self.map, 100)
            self.assertIsNone(result)
            mock_load.assert_called_once_with(mine, None)
            self.assertEqual(self.robot._program_counter, 1)
    
    def test_execute_unload_command(self):
        """Test UNLOAD starts unloading to adjacent destination."""
        storage = Storage(id=20, name='Storage1', pos=(10, 11), capacity=20)
        storage.stored = 5
        self.map.get_adjacent_objects.return_value = [storage]
        
        self.robot._parsed_program = [
            {'command': 'UNLOAD', 'args': [3]},
        ]
        
        with patch.object(self.robot, 'start_unloading') as mock_unload:
            result = self.executor.execute_next_line(self.robot, self.map, 100)
            self.assertIsNone(result)
            mock_unload.assert_called_once_with(storage, 3)
            self.assertEqual(self.robot._program_counter, 1)
    
    def test_execute_send_robots(self):
        """Test SEND broadcasts to robots."""
        robot2 = Robot(id=2, name='Bot2', pos=(15, 15), capacity=5)
        robot2._message_inbox = []
        mine = Mine(id=10, name='Mine1', pos=(20, 20), capacity=10)
        
        self.map.cells = {
            (15, 15): robot2,
            (20, 20): mine,
        }
        
        self.robot._parsed_program = [
            {'command': 'SEND', 'args': ['ROBOTS', 'HELLO']},
        ]
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIsNone(result)
        self.assertEqual(len(robot2._message_inbox), 1)
        self.assertEqual(robot2._message_inbox[0], ('ROBOT', 'HELLO', 100))
        self.assertEqual(self.robot._program_counter, 1)

    def test_execute_goto_object_defaults_stop_distance(self):
        game_map = Map(width=4, height=4)
        robot = Robot(id=1, pos=(0, 0))
        base = Base(id=2, pos=(2, 0))
        game_map.add_object(robot, robot.pos)
        game_map.add_object(base, base.pos)

        robot._program_running = True
        robot._program_counter = 0
        robot._program_labels = {}
        robot._parsed_program = [
            {'command': 'GOTO', 'args': [('object', 2, 0)]},
        ]

        result = self.executor.execute_next_line(robot, game_map, 0)

        self.assertIsNone(result)
        self.assertEqual(robot._move_target, (2, 0))
        self.assertEqual(robot._move_path, [(1, 0)])

    def test_execute_direction_reports_error(self):
        game_map = Map(width=2, height=2)
        robot = Robot(id=1, pos=(0, 0))
        game_map.add_object(robot, robot.pos)

        robot._parsed_program = [
            {'command': 'RIGHT', 'args': [5]},
        ]
        robot._program_running = True
        robot._program_counter = 0

        result = self.executor.execute_next_line(robot, game_map, 0)

        self.assertIn('RIGHT error', result)
        self.assertEqual(robot._program_counter, 1)

    def test_execute_if_scan_true(self):
        game_map = Map(width=4, height=4)
        robot = Robot(id=1, pos=(1, 1))
        base = Base(id=2, pos=(1, 3), stored=1)
        game_map.add_object(robot, robot.pos)
        game_map.add_object(base, base.pos)

        robot._program_running = True
        robot._program_counter = 0
        robot._program_labels = {'YES': 2}
        robot._parsed_program = [
            {'command': 'IF', 'args': [False, 'SCAN', 'D', 2, 'BASE', ':YES']},
            {'command': 'END', 'args': []},
        ]

        result = self.executor.execute_next_line(robot, game_map, 0)

        self.assertIsNone(result)
        self.assertEqual(robot._program_counter, 1)

    def test_execute_if_range_negated(self):
        game_map = Map(width=4, height=4)
        robot = Robot(id=1, pos=(0, 0))
        game_map.add_object(robot, robot.pos)

        robot._program_running = True
        robot._program_counter = 0
        robot._program_labels = {'MISS': 2}
        robot._parsed_program = [
            {'command': 'IF', 'args': [True, 'RANGE', 1, 'ANY', ':MISS']},
            {'command': 'END', 'args': []},
        ]

        result = self.executor.execute_next_line(robot, game_map, 0)

        self.assertIsNone(result)
        self.assertEqual(robot._program_counter, 1)
    
    def test_program_end_reached(self):
        """Test program stops when reaching end."""
        self.robot._parsed_program = [
            {'command': 'WAIT', 'args': [1]},
        ]
        self.robot._program_counter = 1  # past last line
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIn('reached end', result.lower())
        self.assertFalse(self.robot._program_running)
    
    def test_program_not_running(self):
        """Test executor returns message when program not running."""
        self.robot._program_running = False
        self.robot._parsed_program = [{'command': 'END', 'args': []}]
        
        result = self.executor.execute_next_line(self.robot, self.map, 100)
        self.assertIn('not running', result.lower())


class TestRoboBRAINIntegration(unittest.TestCase):
    """Integration tests for parser + executor."""
    
    def test_full_program_execution(self):
        """Test complete program with labels and jumps."""
        program = [
            ':START',
            'IF EMPTY :LOAD',
            'GOTO :UNLOAD',
            ':LOAD',
            'WAIT 5',
            ':UNLOAD',
            'WAIT 10',
            'END',
            '',
            ''
        ]
        
        parsed, labels, errors = RoboBASICParser.parse_program(program)
        self.assertEqual(len(errors), 0)
        self.assertIn('START', labels)
        self.assertIn('LOAD', labels)
        self.assertIn('UNLOAD', labels)
        
        # Execute with empty robot
        robot = Robot(id=1, name='TestBot', pos=(10, 10), capacity=5)
        robot.inventory = 0
        robot._program_running = True
        robot._program_counter = 0
        robot._parsed_program = parsed
        robot._program_labels = labels
        robot._blocked_until = 0.0
        robot._message_inbox = []
        
        game_map = Mock(spec=Map)
        executor = RoboBRAINExecutor()
        
        # Line 1: :START (label, skipped)
        result = executor.execute_next_line(robot, game_map, 100)
        self.assertIsNone(result)
        self.assertEqual(robot._program_counter, 1)
        
        # Line 2: IF EMPTY :LOAD (empty, jump to LOAD at line 4)
        result = executor.execute_next_line(robot, game_map, 100)
        self.assertIsNone(result)
        self.assertEqual(robot._program_counter, 3)  # label LOAD is at line 4, so PC = 3
        
        # Line 4: :LOAD (label, skipped)
        result = executor.execute_next_line(robot, game_map, 100)
        self.assertIsNone(result)
        self.assertEqual(robot._program_counter, 4)
        
        # Line 5: WAIT 5 (blocks)
        result = executor.execute_next_line(robot, game_map, 100)
        self.assertIsNone(result)
        self.assertEqual(robot._blocked_until, 105)
        self.assertEqual(robot._program_counter, 5)


if __name__ == '__main__':
    unittest.main()
