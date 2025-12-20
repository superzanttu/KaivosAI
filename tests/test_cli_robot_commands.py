import tempfile
import unittest
from pathlib import Path

from kaivosai import db, cli
from kaivosai.map import Map
from kaivosai import models


class CLIRobotCommandsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "cli_robot.db"
        self.conn = db.get_game_conn(self.db_path)
        db.init_game_db(self.conn)
        class SimpleClock:
            def __init__(self):
                self.seconds = 0
            def pause(self):
                pass
            def start(self):
                pass
        self.clock = SimpleClock()
        self.game_map = Map(width=10, height=10, conn=self.conn)
        self.controller = cli.CLIController(self.game_map, self.clock, self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def _ensure_robot(self, x=1, y=1):
        self.controller.process_command(f"create robot {x} {y}")
        robot = self.game_map.get((x, y))
        if robot.id is None:
            robot.id = 1
        return robot

    def test_robot_load_with_amount_and_synonyms(self):
        r = self._ensure_robot(1, 1)
        # Place a single adjacent Mine
        self.controller.process_command("create mine 2 1")
        msg = self.controller.process_command(f"robot {r.id} load 2")
        self.assertIn("started loading 2 material", msg)
        # Synonym: take
        msg2 = self.controller.process_command(f"robot {r.id} take 1")
        self.assertIn("started loading 1 material", msg2)

    def test_robot_unload_with_amount_and_synonyms(self):
        r = self._ensure_robot(1, 1)
        # Give robot some inventory
        r.inventory = 3
        # Place a single adjacent Storage
        self.controller.process_command("create storage 2 1")
        msg = self.controller.process_command(f"robot {r.id} unload 2")
        self.assertIn("started unloading 2 material", msg)
        # Synonym: drop
        msg2 = self.controller.process_command(f"robot {r.id} drop 1")
        self.assertIn("started unloading 1 material", msg2)

    def test_robot_movement_aliases_and_distance(self):
        r = self._ensure_robot(1, 1)
        # Alias 'g' and 'move' should be accepted
        msg1 = self.controller.process_command(f"robot {r.id} g 3 3")
        self.assertIn("moving to (3,3)", msg1)
        # Object targeting by ID with explicit distance
        self.controller.process_command("create mine 5 5")
        mine = self.game_map.get((5, 5))
        if getattr(mine, 'id', None) is None:
            mine.id = 99
        msg2 = self.controller.process_command(f"robot {r.id} goto {mine.id} distance 2")
        self.assertIn("stopping 2 cells away", msg2)

    def test_robot_code_editor_unavailable_and_start_pause_synonyms(self):
        r = self._ensure_robot(1, 1)
        # Program editor unavailable in headless mode
        msg_edit = self.controller.process_command(f"robot {r.id} code")
        self.assertIn("Program editor unavailable", msg_edit)
        # Start via synonyms
        r.commands_text = ["END"] + [""] * 9
        msg_start = self.controller.process_command(f"robot {r.id} execute")
        self.assertIn("code started", msg_start)
        # Pause via 'end' synonym
        msg_stop = self.controller.process_command(f"robot {r.id} end")
        self.assertIn("code paused", msg_stop)

    def test_robot_alias_handlers_r_and_bot(self):
        r = self._ensure_robot(2, 2)
        msg_r = self.controller.process_command(f"r {r.id} move 3 2")
        self.assertIn("moving to (3,2)", msg_r)
        msg_bot = self.controller.process_command(f"bot {r.id} go 4 2")
        self.assertIn("moving to (4,2)", msg_bot)

    def test_robot_usage_message_when_missing_action(self):
        r = self._ensure_robot(1, 1)
        msg = self.controller.process_command(f"robot {r.id}")
        self.assertIn("Usage: robot", msg)


if __name__ == "__main__":
    unittest.main()
