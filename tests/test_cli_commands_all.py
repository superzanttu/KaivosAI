import tempfile
import unittest
from pathlib import Path

from kaivosai import db, cli
from kaivosai.map import Map
from kaivosai import models
from kaivosai.exceptions import MapError


class CLIAllCommandsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "cli_all.db"
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

    def _ensure_robot(self, x=1, y=1):
        self.controller.process_command(f"create robot {x} {y}")
        r = self.game_map.get((x, y))
        if r.id is None:
            r.id = 1
        return r

    # Create command
    def test_create_invalid_coordinates_and_type(self):
        msg1 = self.controller.process_command("create robot X Y")
        self.assertIn("Coordinates must be numbers", msg1)
        msg2 = self.controller.process_command("create unknown 1 1")
        self.assertIn("Error: Unknown object type", msg2)

    # Delete command variants
    def test_delete_usage_and_invalid_id(self):
        self.assertIn("Usage: remove", self.controller.process_command("delete"))
        msg = self.controller.process_command("delete id nope")
        self.assertIn("ID must be a number", msg)
        with self.assertRaises(MapError):
            self.controller.process_command("delete id 9999")

    # Move command variants
    def test_move_usage_variants(self):
        self.assertIn("Usage: move X Y to X Y", self.controller.process_command("move 1"))
        # With missing Y after 'to', parser reports number error
        msg_missing = self.controller.process_command("move from 1 1 to 2")
        self.assertIn("Coordinates must be numbers", msg_missing)
        msg_err = self.controller.process_command("move 1 X to 2 2")
        self.assertIn("Coordinates must be numbers", msg_err)

    # Inspect command
    def test_inspect_usage_and_object(self):
        self.assertIn("Usage: inspect", self.controller.process_command("inspect"))
        self.controller.process_command("create base 2 2")
        msg = self.controller.process_command("inspect 2 2")
        self.assertIn("base", msg.lower())

    # System commands
    def test_system_unknown_and_already_optimized(self):
        self.assertIn("Unknown system command", self.controller.process_command("system foo"))
        # Create sequential IDs
        r1 = models.Robot(id=1, pos=(1,1))
        r2 = models.Robot(id=2, pos=(1,2))
        self.game_map.add_object(r1, r1.pos)
        self.game_map.add_object(r2, r2.pos)
        msg = self.controller.process_command("system optimize")
        self.assertIn("already optimized", msg)

    # Map commands
    def test_map_show_list_and_terrain_bounds(self):
        # Top-level 'show' alias maps to 'map' (no sub) -> 'See Map panel'
        self.assertIn("Map panel", self.controller.process_command("show"))
        self.assertIn("Objects panel", self.controller.process_command("map list"))
        self.assertIn("between 0.0 and 1.0", self.controller.process_command("map terrain -0.1"))
        self.assertIn("between 0.0 and 1.0", self.controller.process_command("map terrain 1.1"))
        self.assertIn("Unknown map command", self.controller.process_command("map unknowncmd"))

    # Robot load/unload defaults on bad amount
    def test_robot_load_unload_default_amount(self):
        r = self._ensure_robot(3, 3)
        r.capacity = 5
        r.inventory = 1
        self.controller.process_command("create mine 4 3")
        msg_load = self.controller.process_command(f"robot {r.id} load nope")
        self.assertIn("started loading 4 material", msg_load)
        r.inventory = 3
        self.controller.process_command("create storage 3 4")
        msg_unload = self.controller.process_command(f"robot {r.id} unload nope")
        self.assertIn("started unloading 3 material", msg_unload)


if __name__ == "__main__":
    unittest.main()
