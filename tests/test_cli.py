"""CLI command processing tests for KaivosAI.

These tests exercise the headless CLIController without starting the
Urwid TUI, covering parsing, creation, movement, and legacy commands.
"""
import tempfile
import unittest
from pathlib import Path

from kaivosai import db, cli
from kaivosai.map import Map
from kaivosai import VERSION
from kaivosai import models


class FakeClock:
    """Minimal clock stub for CLI tests."""

    def __init__(self):
        self.seconds = 0
        self.running = True

    def start(self):
        self.running = True

    def pause(self):
        self.running = False

    def reset(self):
        self.seconds = 0


class CLIControllerTests(unittest.TestCase):
    """Validate CLIController command handling without Urwid UI."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.conn = db.get_game_conn(self.db_path)
        db.init_game_db(self.conn)
        self.clock = FakeClock()
        self.game_map = Map(width=10, height=10, conn=self.conn)
        self.controller = cli.CLIController(self.game_map, self.clock, self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_help_command_returns_text(self):
        msg = self.controller.process_command("help")
        self.assertIn("Commands", msg)
        self.assertIn("ROBOT CONTROL", msg)

    def test_system_version_command(self):
        msg = self.controller.process_command("system version")
        self.assertIn(VERSION, msg)

    def test_create_inspect_and_delete(self):
        create_msg = self.controller.process_command("create robot 2 2")
        self.assertIn("Created robot", create_msg)

        inspect_msg = self.controller.process_command("inspect 2 2")
        self.assertIn("robot", inspect_msg.lower())

        delete_msg = self.controller.process_command("delete 2 2")
        self.assertIn("Removed", delete_msg)
        self.assertIsNone(self.game_map.get((2, 2)))

    def test_move_object(self):
        self.controller.process_command("create mine 1 1")
        move_msg = self.controller.process_command("move 1 1 to 2 2")
        self.assertIn("Moved from (1,1) to (2,2)", move_msg)
        self.assertIsInstance(self.game_map.get((2, 2)), models.Mine)

    def test_robot_movement_sets_path(self):
        self.controller.process_command("create robot 1 1")
        robot = self.game_map.get((1, 1))
        # ID should be assigned via persistence when a DB connection is present
        if robot.id is None:
            robot.id = 1
        move_msg = self.controller.process_command(f"robot {robot.id} goto 2 2")
        self.assertIn("moving to (2,2)", move_msg)
        self.assertEqual(robot._move_target, (2, 2))
        self.assertTrue(getattr(robot, "_move_path", []))

    def test_map_terrain_invalid_density(self):
        msg = self.controller.process_command("map terrain nope")
        self.assertIn("Density must be a number", msg)

    def test_legacy_list_redirect(self):
        msg = self.controller.process_command("list")
        self.assertIn("Objects panel", msg)

    def test_map_reset_clears_state(self):
        self.controller.process_command("create mine 3 3")
        self.clock.seconds = 42

        msg = self.controller.process_command("map reset")

        self.assertEqual(self.clock.seconds, 0)
        self.assertEqual(len(self.game_map.cells), 0)
        self.assertIn("reset", msg.lower())

    def test_map_terrain_success(self):
        msg = self.controller.process_command("map terrain 0.1 1")
        self.assertIn("Terrain generated", msg)

    def test_robot_id_validation(self):
        msg = self.controller.process_command("robot not-a-number goto 1 1")
        self.assertIn("Robot ID must be a number", msg)

    def test_pause_resume_top_level_and_system(self):
        # Top-level pause/resume
        msg1 = self.controller.process_command("pause")
        self.assertIn("Clock paused", msg1)
        msg2 = self.controller.process_command("resume")
        self.assertIn("Clock resumed", msg2)

        # System pause/resume
        msg3 = self.controller.process_command("system pause")
        self.assertIn("Clock paused", msg3)
        msg4 = self.controller.process_command("system resume")
        self.assertIn("Clock resumed", msg4)

    def test_version_and_help_top_level(self):
        v = self.controller.process_command("version")
        self.assertIn("KaivosAI version", v)
        h = self.controller.process_command("help")
        self.assertIn("ROBOT CONTROL", h)

    def test_unknown_command_message(self):
        msg = self.controller.process_command("this-command-does-not-exist 123")
        self.assertIn("don't understand", msg.lower())

    def test_robot_program_start_and_stop(self):
        # Prepare robot
        self.controller.process_command("create robot 1 1")
        robot = self.game_map.get((1, 1))
        robot.id = robot.id or 1
        # Invalid program (too long line) should not start
        robot.commands_text = ["X" * 25] + [""] * 9
        msg = self.controller.process_command(f"robot {robot.id} run")
        self.assertIn("Cannot start program", msg)
        # Valid minimal program starts
        robot.commands_text = ["END"] + [""] * 9
        msg2 = self.controller.process_command(f"robot {robot.id} run")
        self.assertIn("code started", msg2)
        # Stop
        msg3 = self.controller.process_command(f"robot {robot.id} halt")
        self.assertIn("code paused", msg3)

    def test_system_optimize_ids(self):
        # Create objects with non-sequential IDs
        r1 = models.Robot(id=10, pos=(2, 2))
        r2 = models.Robot(id=20, pos=(3, 3))
        self.game_map.add_object(r1, r1.pos)
        self.game_map.add_object(r2, r2.pos)

        msg = self.controller.process_command("system optimize")
        self.assertIn("Optimized", msg)


if __name__ == "__main__":
    unittest.main()
