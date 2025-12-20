import tempfile
import unittest
from pathlib import Path

from kaivosai import db
from kaivosai.clock import GameClock


class GameClockTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "clock.db"
        conn = db.get_game_conn(self.db_path)
        db.init_game_db(conn)
        self.clock = GameClock(conn)

    def tearDown(self):
        try:
            self.clock.stop()
        except Exception:
            pass
        try:
            # Close both dedicated and original connections to release file handles
            if getattr(self.clock, 'conn', None):
                self.clock.conn.close()
            if getattr(self.clock, '_orig_conn', None):
                self.clock._orig_conn.close()
        except Exception:
            pass
        self.tmpdir.cleanup()

    def test_seconds_running_and_format(self):
        self.clock.seconds = 3661  # 1h 1m 1s
        self.clock.running = True
        self.assertTrue(self.clock.running)
        formatted = self.clock.format()
        self.assertIn("Week 1 Day 1 01:01:01", formatted)

        self.clock.running = False
        self.assertFalse(self.clock.running)

    def test_reset_updates_epoch_and_seconds(self):
        self.clock.seconds = 42
        before_epoch = self.clock.epoch_initialized
        self.clock.reset()
        self.assertEqual(self.clock.seconds, 0)
        self.assertNotEqual(before_epoch, self.clock.epoch_initialized)

    def test_start_creates_thread_and_stop_joins(self):
        self.clock.start()
        self.assertIsNotNone(self.clock._thread)
        self.assertTrue(self.clock._thread.is_alive())

        self.clock.stop()
        self.assertFalse(self.clock._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
