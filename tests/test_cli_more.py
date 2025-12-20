import tempfile
import unittest
from pathlib import Path

from kaivosai import db, cli
from kaivosai.map import Map


class CLIMoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "cli_more.db"
        self.conn = db.get_game_conn(self.db_path)
        db.init_game_db(self.conn)
        self.game_map = Map(width=10, height=10, conn=self.conn)
        class SimpleClock:
            def __init__(self):
                self.seconds = 0
            def pause(self):
                pass
            def start(self):
                pass
        self.clock = SimpleClock()
        self.controller = cli.CLIController(self.game_map, self.clock, self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_delete_variants(self):
        self.controller.process_command("create mine 2 2")
        msg1 = self.controller.process_command("delete at 2 2")
        self.assertIn("Removed", msg1)

        self.controller.process_command("create storage 3 3")
        obj = self.game_map.get((3, 3))
        oid = getattr(obj, 'id', None) or 1
        obj.id = oid
        msg2 = self.controller.process_command(f"delete id {oid}")
        self.assertIn("Removed", msg2)

        self.controller.process_command("create base 4 4")
        obj2 = self.game_map.get((4, 4))
        oid2 = getattr(obj2, 'id', None) or 2
        obj2.id = oid2
        msg3 = self.controller.process_command(f"delete {oid2}")
        self.assertIn("Removed", msg3)

        msg4 = self.controller.process_command("delete X Y")
        self.assertIn("Invalid", msg4)

    def test_move_from_to_and_errors(self):
        self.controller.process_command("create robot 1 1")
        msg_err = self.controller.process_command("move from 1 1 to 1")
        self.assertIn("Coordinates must be numbers", msg_err)
        msg_ok = self.controller.process_command("move 1 1 to 2 2")
        self.assertIn("Moved from (1,1) to (2,2)", msg_ok)

    def test_inspect_nothing(self):
        msg = self.controller.process_command("inspect 9 9")
        self.assertIn("Nothing", msg)

    def test_map_terrain_invalid_cluster_size(self):
        msg = self.controller.process_command("map terrain 0.1 0")
        self.assertIn("Cluster size", msg)

    def test_map_demo_and_quit(self):
        msg = self.controller.process_command("map demo")
        self.assertIn("Added", msg)
        # Quit should raise ExitMainLoop
        import urwid
        with self.assertRaises(urwid.ExitMainLoop):
            self.controller.process_command("quit")


if __name__ == "__main__":
    unittest.main()
