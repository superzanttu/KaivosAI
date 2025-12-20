import tempfile
import unittest
from pathlib import Path

from kaivosai import db, cli
from kaivosai.map import Map
from kaivosai import models


class CLIEdgesTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "cli_edges.db"
        self.conn = db.get_game_conn(self.db_path)
        db.init_game_db(self.conn)
        class SimpleClock:
            def __init__(self):
                self.seconds = 0
            def pause(self):
                pass
            def start(self):
                pass
            def reset(self):
                self.seconds = 0
        self.clock = SimpleClock()
        self.game_map = Map(width=10, height=10, conn=self.conn)
        self.controller = cli.CLIController(self.game_map, self.clock, self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_top_level_alias_messages(self):
        self.assertIn("map", self.controller.process_command("terrain").lower())
        self.assertIn("objects panel", self.controller.process_command("list").lower())
        self.assertIn("map reset", self.controller.process_command("reset"))
        self.assertIn("map demo", self.controller.process_command("demo"))

    def test_inspect_invalid_coordinates(self):
        msg = self.controller.process_command("inspect X Y")
        self.assertIn("must be numbers", msg)

    def _ensure_robot_with_id(self, x=1, y=1):
        self.controller.process_command(f"create robot {x} {y}")
        robot = self.game_map.get((x, y))
        if robot.id is None:
            # Persist via add_object already assigns ID when conn present, fallback
            robot.id = 1
        return robot

    def test_robot_movement_distance_keyword_errors(self):
        robot = self._ensure_robot_with_id()
        msg1 = self.controller.process_command(f"robot {robot.id} goto 5 5 distance")
        self.assertIn("requires a number", msg1)
        msg2 = self.controller.process_command(f"robot {robot.id} goto 5 5 distance nope")
        self.assertIn("must be a number", msg2)

    def test_robot_movement_object_id_errors(self):
        robot = self._ensure_robot_with_id()
        msg1 = self.controller.process_command(f"robot {robot.id} goto Z")
        self.assertIn("Object ID must be a number", msg1)
        msg2 = self.controller.process_command(f"robot {robot.id} goto 9999")
        self.assertIn("not found", msg2.lower())

    def test_robot_movement_cannot_target_robot(self):
        r1 = self._ensure_robot_with_id(1, 1)
        # Create second robot adjacent
        self.controller.process_command("create robot 2 1")
        r2 = self.game_map.get((2, 1))
        if r2.id is None:
            r2.id = (r1.id or 1) + 1
        msg = self.controller.process_command(f"robot {r1.id} goto {r2.id}")
        self.assertIn("Cannot target robots", msg)

    def test_robot_movement_no_path_or_at_target(self):
        robot = self._ensure_robot_with_id(3, 3)
        msg = self.controller.process_command(f"robot {robot.id} goto 3 3")
        self.assertIn("No path", msg)

    def test_robot_load_unload_adjacent_validation(self):
        robot = self._ensure_robot_with_id(5, 5)
        # No adjacent objects
        msg_load_none = self.controller.process_command(f"robot {robot.id} load")
        self.assertIn("No adjacent objects", msg_load_none)
        # Place two adjacent valid targets to trigger multiple-adjacent error
        self.game_map.add_object(models.Storage(pos=(6,5)), (6, 5))
        self.game_map.add_object(models.Base(pos=(5,6)), (5, 6))
        msg_unload_multi = self.controller.process_command(f"robot {robot.id} unload")
        self.assertIn("Multiple adjacent objects", msg_unload_multi)


if __name__ == "__main__":
    unittest.main()
