import tempfile
import sqlite3
import tempfile
import sqlite3
from pathlib import Path
import unittest

from kaivosai.db import init_game_db
from kaivosai.map import Map
from kaivosai.models import Mine, Storage, Robot


class PersistenceTests(unittest.TestCase):
    def test_map_persist_and_load(self):
        tf = tempfile.NamedTemporaryFile(delete=False)
        tf.close()
        dbp = Path(tf.name)
        conn = sqlite3.connect(str(dbp))
        conn.row_factory = sqlite3.Row
        init_game_db(conn)
        game_map = Map(width=10, height=10, conn=conn)
        m = Mine(name='T1', pos=(1, 1), durability=5)
        s = Storage(name='S1', pos=(2, 2), capacity=20)
        r = Robot(pos=(3, 3), capacity=5)
        game_map.add_object(m, m.pos)
        game_map.add_object(s, s.pos)
        game_map.add_object(r, r.pos)
        conn.close()
        conn2 = sqlite3.connect(str(dbp))
        conn2.row_factory = sqlite3.Row
        game_map2 = Map(width=10, height=10, conn=conn2)
        self.assertIn((1, 1), game_map2.cells)
        self.assertIn((2, 2), game_map2.cells)
        self.assertIn((3, 3), game_map2.cells)
        conn2.close()

