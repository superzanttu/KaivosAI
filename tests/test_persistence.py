import tempfile
import sqlite3
from pathlib import Path
import unittest

from kaivosai.db import init_game_db, persist_object
from kaivosai.map import Map
from kaivosai.models import Mine, Storage, Robot
from kaivosai.migrations import migrate_deduplicate


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

    def test_move_update_and_remove(self):
        tf = tempfile.NamedTemporaryFile(delete=False)
        tf.close()
        dbp = Path(tf.name)
        conn = sqlite3.connect(str(dbp))
        conn.row_factory = sqlite3.Row
        init_game_db(conn)
        game_map = Map(width=10, height=10, conn=conn)
        m = Mine(name='MoveMe', pos=(1, 1), durability=7)
        game_map.add_object(m, m.pos)

        # Move
        game_map.move_object((1, 1), (2, 2))
        # Update a property and persist
        moved = game_map.get((2, 2))
        moved.name = 'MovedMine'
        persist_object(conn, moved)

        # Remove
        game_map.remove_object((2, 2))

        conn.close()

        # Verify after reopen: removed
        conn2 = sqlite3.connect(str(dbp))
        conn2.row_factory = sqlite3.Row
        game_map2 = Map(width=10, height=10, conn=conn2)
        self.assertNotIn((2, 2), game_map2.cells)
        conn2.close()

    def test_migration_deduplicate(self):
        # Create an old-style DB without UNIQUE constraint and with duplicates
        tf = tempfile.NamedTemporaryFile(delete=False)
        tf.close()
        dbp = Path(tf.name)
        conn = sqlite3.connect(str(dbp))
        conn.execute(
            '''
            CREATE TABLE game_objects (
                id INTEGER PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                capacity INTEGER,
                stored INTEGER,
                durability INTEGER,
                bank INTEGER,
                inventory INTEGER
            )
            '''
        )
        # Insert two rows at same coordinates (other fields NULL)
        conn.execute("INSERT INTO game_objects (id,type,name,x,y) VALUES (1,'mine','A',5,5)")
        conn.execute("INSERT INTO game_objects (id,type,name,x,y) VALUES (2,'mine','B',5,5)")
        conn.commit()
        conn.close()

        before, after = migrate_deduplicate(dbp)
        self.assertEqual(before, 2)
        self.assertEqual(after, 1)

        # Verify the DB now has a single row for (5,5)
        conn2 = sqlite3.connect(str(dbp))
        cur = conn2.execute('SELECT COUNT(*) FROM game_objects WHERE x = ? AND y = ?', (5, 5))
        c = cur.fetchone()[0]
        conn2.close()
        self.assertEqual(c, 1)

    def test_remove_by_id(self):
        tf = tempfile.NamedTemporaryFile(delete=False)
        tf.close()
        dbp = Path(tf.name)
        conn = sqlite3.connect(str(dbp))
        conn.row_factory = sqlite3.Row
        init_game_db(conn)
        game_map = Map(width=10, height=10, conn=conn)
        m = Mine(name='DeleteMe', pos=(4, 4), durability=3)
        game_map.add_object(m, m.pos)
        oid = getattr(m, 'id', None)
        self.assertIsNotNone(oid)

        removed = game_map.remove_object(oid)
        self.assertIsNotNone(removed)

        conn.close()

        conn2 = sqlite3.connect(str(dbp))
        conn2.row_factory = sqlite3.Row
        game_map2 = Map(width=10, height=10, conn=conn2)
        self.assertNotIn((4, 4), game_map2.cells)
        conn2.close()

