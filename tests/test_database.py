"""Comprehensive database layer tests for KaivosAI.

Tests all database operations including:
- Persistence (persist_object, delete, load)
- Migration (deduplicate, backup)
- Game_meta table (key-value storage)
- Event logging
- Schema initialization
"""
import unittest
import sqlite3
import tempfile
from pathlib import Path
from kaivosai import db, models, migrations


class DatabaseInitializationTests(unittest.TestCase):
    """Tests for database connection and schema initialization."""
    
    def test_get_game_conn_creates_db(self):
        """Test database file creation and connection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = db.get_game_conn(db_path)
            self.assertTrue(db_path.exists())
            conn.close()
    
    def test_init_game_db_creates_tables(self):
        """Test that init_game_db creates all required tables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = db.get_game_conn(db_path)
            db.init_game_db(conn)
            
            # Verify tables exist
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
            
            self.assertIn('game_objects', tables)
            self.assertIn('game_meta', tables)
            self.assertIn('game_events', tables)
            conn.close()
    
    def test_init_game_db_idempotent(self):
        """Test that init_game_db can be called multiple times safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = db.get_game_conn(db_path)
            
            # Call init twice
            db.init_game_db(conn)
            db.init_game_db(conn)
            
            # Should still have valid schema
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
            self.assertGreaterEqual(len(tables), 3)  # game_objects, game_meta, game_events (plus sqlite_sequence if AUTOINCREMENT used)
            conn.close()
    
    def test_unique_constraint_on_position(self):
        """Test that UNIQUE(x,y) constraint exists on game_objects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = db.get_game_conn(db_path)
            db.init_game_db(conn)
            
            # Insert first object at (5, 5)
            conn.execute(
                "INSERT INTO game_objects (type, name, x, y) VALUES (?, ?, ?, ?)",
                ('robot', 'Bot1', 5, 5)
            )
            conn.commit()
            
            # Try to insert second object at same position - should use UPSERT
            robot2 = models.Robot(id=None, name='Bot2', pos=(5, 5), inventory=0)
            db.persist_object(conn, robot2)
            
            # Should only have one object at (5, 5)
            cursor = conn.execute("SELECT COUNT(*) FROM game_objects WHERE x=5 AND y=5")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
            
            # And it should be Bot2 (the latest)
            cursor = conn.execute("SELECT name FROM game_objects WHERE x=5 AND y=5")
            name = cursor.fetchone()[0]
            self.assertEqual(name, 'Bot2')
            conn.close()


class DatabasePersistenceTests(unittest.TestCase):
    """Tests for object persistence operations."""
    
    def setUp(self):
        """Create temporary database for each test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.conn = db.get_game_conn(self.db_path)
        db.init_game_db(self.conn)
    
    def tearDown(self):
        """Close connection and cleanup temporary directory."""
        self.conn.close()
        self.tmpdir.cleanup()
    
    def test_persist_robot(self):
        """Test persisting a Robot object."""
        robot = models.Robot(id=None, name='TestBot', pos=(10, 10), inventory=5)
        db.persist_object(self.conn, robot)
        
        # Verify object was saved
        cursor = self.conn.execute("SELECT * FROM game_objects WHERE x=10 AND y=10")
        row = cursor.fetchone()
        
        self.assertIsNotNone(row)
        self.assertEqual(row['type'], 'robot')
        self.assertEqual(row['name'], 'TestBot')
        self.assertEqual(row['inventory'], 5)
        # Robot doesn't have bank field, only Base does
    
    def test_persist_mine(self):
        """Test persisting a Mine object."""
        mine = models.Mine(id=None, name='Mine1', pos=(15, 15), stored=3, capacity=10)
        db.persist_object(self.conn, mine)
        
        cursor = self.conn.execute("SELECT * FROM game_objects WHERE x=15 AND y=15")
        row = cursor.fetchone()
        
        self.assertEqual(row['type'], 'mine')
        self.assertEqual(row['stored'], 3)
        self.assertEqual(row['capacity'], 10)
    
    def test_persist_storage(self):
            # Robot doesn't have bank field, only Base does
        storage = models.Storage(id=None, name='Store1', pos=(20, 20), stored=15, capacity=20)
        db.persist_object(self.conn, storage)
        
        cursor = self.conn.execute("SELECT * FROM game_objects WHERE x=20 AND y=20")
        row = cursor.fetchone()
        
        self.assertEqual(row['type'], 'storage')
        self.assertEqual(row['stored'], 15)
        self.assertEqual(row['capacity'], 20)
    
    def test_persist_base(self):
        """Test persisting a Base object."""
        base = models.Base(id=None, name='HQ', pos=(25, 25), stored=8)
        db.persist_object(self.conn, base)
        
        cursor = self.conn.execute("SELECT * FROM game_objects WHERE x=25 AND y=25")
        row = cursor.fetchone()
        
        self.assertEqual(row['type'], 'base')
        self.assertEqual(row['stored'], 8)
    
    def test_persist_rock(self):
        """Test persisting a Rock object."""
        rock = models.Rock(id=None, pos=(30, 30))
        db.persist_object(self.conn, rock)
        
        cursor = self.conn.execute("SELECT * FROM game_objects WHERE x=30 AND y=30")
        row = cursor.fetchone()
        
        self.assertEqual(row['type'], 'rock')
        
    
    def test_persist_updates_existing_object(self):
        """Test that persist_object updates object at same position (UPSERT)."""
        robot1 = models.Robot(id=None, name='Bot1', pos=(5, 5), inventory=1)
        db.persist_object(self.conn, robot1)
        
        robot2 = models.Robot(id=None, name='Bot2', pos=(5, 5), inventory=2)
        db.persist_object(self.conn, robot2)
        
        # Should only have one object at (5, 5)
        cursor = self.conn.execute("SELECT COUNT(*) FROM game_objects WHERE x=5 AND y=5")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 1)
        
        # Should be the updated object
        cursor = self.conn.execute("SELECT * FROM game_objects WHERE x=5 AND y=5")
        row = cursor.fetchone()
        self.assertEqual(row['name'], 'Bot2')
        self.assertEqual(row['inventory'], 2)
    
    def test_persist_assigns_id_to_object(self):
        """Test that persist_object assigns database ID to object."""
        robot = models.Robot(id=None, name='Bot', pos=(7, 7), inventory=0)
        self.assertIsNone(robot.id)
        
        db.persist_object(self.conn, robot)
        
        # Object should now have an ID
        self.assertIsNotNone(robot.id)
        self.assertIsInstance(robot.id, int)
    
    def test_delete_object_by_position(self):
        """Test deleting object by position."""
        robot = models.Robot(id=None, name='Bot', pos=(10, 10), inventory=0)
        db.persist_object(self.conn, robot)
        
        # Verify it exists
        cursor = self.conn.execute("SELECT COUNT(*) FROM game_objects WHERE x=10 AND y=10")
        self.assertEqual(cursor.fetchone()[0], 1)
        
        # Delete it
        db.delete_object_db(self.conn, (10, 10))
        
        # Verify it's gone
        cursor = self.conn.execute("SELECT COUNT(*) FROM game_objects WHERE x=10 AND y=10")
        self.assertEqual(cursor.fetchone()[0], 0)
    
    def test_delete_object_by_id(self):
        """Test deleting object by ID."""
        robot = models.Robot(id=None, name='Bot', pos=(12, 12), inventory=0)
        db.persist_object(self.conn, robot)
        
        obj_id = robot.id
        
        # Delete by ID
        db.delete_object_by_id(self.conn, obj_id)
        
        # Verify it's gone
        cursor = self.conn.execute("SELECT COUNT(*) FROM game_objects WHERE id=?", (obj_id,))
        self.assertEqual(cursor.fetchone()[0], 0)
    
    def test_delete_nonexistent_object(self):
        """Test that deleting nonexistent object doesn't raise error."""
        # Should not raise
        db.delete_object_db(self.conn, (999, 999))
        db.delete_object_by_id(self.conn, 9999)
    
    def test_load_objects_from_db(self):
        """Test loading all objects from database."""
        # Create multiple objects
        robot = models.Robot(id=None, name='Bot', pos=(1, 1), inventory=0)
        mine = models.Mine(id=None, name='Mine', pos=(2, 2), stored=5, capacity=10)
        storage = models.Storage(id=None, name='Store', pos=(3, 3), stored=10, capacity=20)
        
        db.persist_object(self.conn, robot)
        db.persist_object(self.conn, mine)
        db.persist_object(self.conn, storage)
        
        # Load all
        rows = db.load_objects_from_db(self.conn)
        
        self.assertEqual(len(rows), 3)
        types = {row['type'] for row in rows}
        self.assertEqual(types, {'robot', 'mine', 'storage'})
    
    def test_load_empty_database(self):
        """Test loading from empty database returns empty list."""
        rows = db.load_objects_from_db(self.conn)
        self.assertEqual(len(rows), 0)


class DatabaseMetaTableTests(unittest.TestCase):
    """Tests for game_meta key-value table."""
    
    def setUp(self):
        """Create temporary database for each test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.conn = db.get_game_conn(self.db_path)
        db.init_game_db(self.conn)
    
    def tearDown(self):
        """Close connection and cleanup temporary directory."""
        self.conn.close()
        self.tmpdir.cleanup()
    
    def test_store_and_retrieve_meta_value(self):
        """Test storing and retrieving key-value pairs."""
        self.conn.execute(
            "INSERT INTO game_meta (key, value) VALUES (?, ?)",
            ('game_seconds', '12345')
        )
        self.conn.commit()
        
        cursor = self.conn.execute("SELECT value FROM game_meta WHERE key=?", ('game_seconds',))
        row = cursor.fetchone()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], '12345')
    
    def test_update_meta_value(self):
        """Test updating existing meta value."""
        self.conn.execute(
            "INSERT INTO game_meta (key, value) VALUES (?, ?)",
            ('clock_state', 'running')
        )
        self.conn.commit()
        
        # Update
        self.conn.execute(
            "UPDATE game_meta SET value=? WHERE key=?",
            ('paused', 'clock_state')
        )
        self.conn.commit()
        
        cursor = self.conn.execute("SELECT value FROM game_meta WHERE key=?", ('clock_state',))
        row = cursor.fetchone()
        self.assertEqual(row[0], 'paused')
    
    def test_delete_meta_value(self):
        """Test deleting meta value."""
        self.conn.execute(
            "INSERT INTO game_meta (key, value) VALUES (?, ?)",
            ('temp_key', 'temp_value')
        )
        self.conn.commit()
        
        self.conn.execute("DELETE FROM game_meta WHERE key=?", ('temp_key',))
        self.conn.commit()
        
        cursor = self.conn.execute("SELECT COUNT(*) FROM game_meta WHERE key=?", ('temp_key',))
        count = cursor.fetchone()[0]
        self.assertEqual(count, 0)
    
    def test_primary_key_constraint(self):
        """Test that key is a primary key (no duplicates)."""
        self.conn.execute(
            "INSERT INTO game_meta (key, value) VALUES (?, ?)",
            ('unique_key', 'value1')
        )
        self.conn.commit()
        
        # Try to insert duplicate key - should fail
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO game_meta (key, value) VALUES (?, ?)",
                ('unique_key', 'value2')
            )


class DatabaseEventLogTests(unittest.TestCase):
    """Tests for event logging system."""
    
    def setUp(self):
        """Create temporary database for each test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        self.conn = db.get_game_conn(self.db_path)
        db.init_game_db(self.conn)
    
    def tearDown(self):
        """Close connection and cleanup temporary directory."""
        self.conn.close()
        self.tmpdir.cleanup()
    
    def test_log_simple_event(self):
        """Test logging a simple event without object."""
        db.log_event(self.conn, 100.0, 'test_event', 'Test message')
        
        cursor = self.conn.execute("SELECT * FROM game_events")
        row = cursor.fetchone()
        
        self.assertIsNotNone(row)
        self.assertEqual(row['timestamp'], 100.0)
        self.assertEqual(row['event_type'], 'test_event')
        self.assertEqual(row['message'], 'Test message')
    
    def test_log_event_with_object(self):
        """Test logging event with associated object."""
        robot = models.Robot(id=42, name='Bot', pos=(5, 5), inventory=0)
        db.log_event(self.conn, 200.0, 'robot_move', 'Robot moved', obj=robot, pos=robot.pos)
        
        cursor = self.conn.execute("SELECT * FROM game_events")
        row = cursor.fetchone()
        
        self.assertEqual(row['object_id'], 42)
        self.assertEqual(row['object_type'], 'robot')
        self.assertEqual(row['x'], 5)
        self.assertEqual(row['y'], 5)
    
    def test_log_event_with_position(self):
        """Test logging event with explicit position."""
        db.log_event(self.conn, 300.0, 'terrain_gen', 'Rock placed', pos=(10, 15))
        
        cursor = self.conn.execute("SELECT * FROM game_events")
        row = cursor.fetchone()
        
        self.assertEqual(row['x'], 10)
        self.assertEqual(row['y'], 15)
    
    def test_get_recent_events_empty(self):
        """Test getting events from empty table."""
        events = db.get_recent_events(self.conn, limit=10)
        self.assertEqual(len(events), 0)
    
    def test_get_recent_events_order(self):
        """Test that events are returned oldest first."""
        # Log events in sequence
        db.log_event(self.conn, 100.0, 'event1', 'First event')
        db.log_event(self.conn, 200.0, 'event2', 'Second event')
        db.log_event(self.conn, 300.0, 'event3', 'Third event')
        
        events = db.get_recent_events(self.conn, limit=10)
        
        # Should be oldest first, newest last
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]['event_type'], 'event1')
        self.assertEqual(events[1]['event_type'], 'event2')
        self.assertEqual(events[2]['event_type'], 'event3')
    
    def test_get_recent_events_limit(self):
        """Test that limit parameter works correctly."""
        # Log 5 events
        for i in range(5):
            db.log_event(self.conn, float(i * 100), f'event{i}', f'Event {i}')
        
        # Request only 3
        events = db.get_recent_events(self.conn, limit=3)
        
        self.assertEqual(len(events), 3)
        # Should get the 3 most recent (oldest first in result)
        self.assertEqual(events[0]['event_type'], 'event2')
        self.assertEqual(events[1]['event_type'], 'event3')
        self.assertEqual(events[2]['event_type'], 'event4')
    
    def test_event_index_exists(self):
        """Test that timestamp index exists for performance."""
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_events_timestamp'"
        )
        index = cursor.fetchone()
        self.assertIsNotNone(index)


class DatabaseMigrationTests(unittest.TestCase):
    """Tests for database migrations."""
    
    def test_backup_db_creates_backup_file(self):
        """Test that backup creates .bak file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # Create a database
            conn = db.get_game_conn(db_path)
            db.init_game_db(conn)
            conn.close()
            
            # Backup
            bak_path = migrations.backup_db(db_path)
            
            self.assertTrue(bak_path.exists())
            self.assertEqual(bak_path.name, 'test.db.bak')
    
    def test_backup_preserves_content(self):
        """Test that backup file contains same data as original."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # Create database with data
            conn = db.get_game_conn(db_path)
            db.init_game_db(conn)
            robot = models.Robot(id=None, name='Bot', pos=(1, 1), inventory=0)
            db.persist_object(conn, robot)
            conn.close()
            
            # Backup
            bak_path = migrations.backup_db(db_path)
            
            # Verify backup has same data
            bak_conn = db.get_game_conn(bak_path)
            cursor = bak_conn.execute("SELECT COUNT(*) FROM game_objects")
            count = cursor.fetchone()[0]
            bak_conn.close()
            
            self.assertEqual(count, 1)
    
    def test_migrate_deduplicate_removes_duplicates(self):
        """Test that migration removes duplicate objects at same position."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # Create database with duplicate positions
            conn = db.get_game_conn(db_path)
            
            # Create table WITHOUT unique constraint (simulate old DB)
            conn.execute(
                """
                CREATE TABLE game_objects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                """
            )
            
            # Insert duplicates at (5, 5)
            conn.execute(
                "INSERT INTO game_objects (type, name, x, y) VALUES (?, ?, ?, ?)",
                ('robot', 'Bot1', 5, 5)
            )
            conn.execute(
                "INSERT INTO game_objects (type, name, x, y) VALUES (?, ?, ?, ?)",
                ('robot', 'Bot2', 5, 5)
            )
            conn.execute(
                "INSERT INTO game_objects (type, name, x, y) VALUES (?, ?, ?, ?)",
                ('mine', 'Mine1', 10, 10)
            )
            conn.commit()
            conn.close()
            
            # Run migration
            before, after = migrations.migrate_deduplicate(db_path)
            
            self.assertEqual(before, 3)
            self.assertEqual(after, 2)  # One duplicate removed
            
            # Verify only one object at (5, 5)
            conn = db.get_game_conn(db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM game_objects WHERE x=5 AND y=5")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
            
            # Verify it kept the one with highest ID (Bot2)
            cursor = conn.execute("SELECT name FROM game_objects WHERE x=5 AND y=5")
            name = cursor.fetchone()[0]
            self.assertEqual(name, 'Bot2')
            conn.close()
    
    def test_migrate_deduplicate_nonexistent_db(self):
        """Test migration on nonexistent database returns (0, 0)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nonexistent.db"
            before, after = migrations.migrate_deduplicate(db_path)
            self.assertEqual(before, 0)
            self.assertEqual(after, 0)
    
    def test_migrate_creates_backup(self):
        """Test that migration creates backup before modifying."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # Create simple database
            conn = db.get_game_conn(db_path)
            db.init_game_db(conn)
            conn.close()
            
            # Run migration
            migrations.migrate_deduplicate(db_path)
            
            # Backup should exist
            bak_path = db_path.with_suffix(db_path.suffix + '.bak')
            self.assertTrue(bak_path.exists())


if __name__ == '__main__':
    unittest.main()
