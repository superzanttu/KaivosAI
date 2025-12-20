import tempfile
import sqlite3
from pathlib import Path
import unittest

from kaivosai.db import init_game_db, get_game_conn, get_recent_events
from kaivosai.map import Map
from kaivosai.models import Robot, Rock, Base


class MapMoreTests(unittest.TestCase):
    def test_neighbors_center_and_edges(self):
        game_map = Map(width=3, height=3)
        self.assertEqual(len(game_map._neighbors((1, 1))), 4)
        self.assertEqual(len(game_map._neighbors((0, 0))), 2)
        self.assertEqual(len(game_map._neighbors((2, 2))), 2)

    def test_find_path_start_is_goal(self):
        game_map = Map(width=5, height=5)
        self.assertEqual(game_map._find_path((2, 2), (2, 2)), [])

    def test_generate_terrain_zero_density(self):
        game_map = Map(width=6, height=6)
        border, terrain = game_map.generate_full_terrain(rock_density=0.0, cluster_size=3)
        self.assertGreater(border, 0)
        self.assertEqual(terrain, 0)
        self.assertIsInstance(game_map.get((0, 0)), Rock)
        self.assertIsInstance(game_map.get((5, 5)), Rock)

    def test_tick_movement_arrival_logs(self):
        # With a DB to verify event logging
        tf = tempfile.NamedTemporaryFile(delete=False)
        tf.close()
        dbp = Path(tf.name)
        conn = get_game_conn(dbp)
        init_game_db(conn)
        game_map = Map(width=5, height=5, conn=conn)

        robot = Robot(id=1, pos=(0, 0))
        game_map.add_object(robot, robot.pos)
        game_map.command_move_robot(1, (1, 0))

        # Simulate tick; arrival should be logged when reaching target
        game_map.tick_movement()
        events = get_recent_events(conn, limit=5)
        self.assertTrue(any(e[3] == 'robot_arrived' for e in events))
        conn.close()


if __name__ == "__main__":
    unittest.main()
