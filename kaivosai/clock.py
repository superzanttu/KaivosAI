"""Game clock for KaivosAI.

Provides a persistent, ticking game clock stored in `game_meta` table.
Clock counts seconds; weeks are 7-day blocks. Time format shown as
"Week W Day D HH:MM:SS". The clock persists `game_seconds`,
`game_running` and `epoch_initialized` in `game_meta`.

Threading:
    - GameClock runs in a separate background thread
    - Uses dedicated connection with check_same_thread=False
    - Main thread + GameClock thread = 2 total threads
    - Shared database via SQLite WAL mode for concurrency
    
Example:
    >>> conn = get_game_conn()
    >>> clock = GameClock(conn)
    >>> clock.start()
    >>> clock.pause()
    >>> clock.resume()
    >>> clock.stop()
"""
from __future__ import annotations
from threading import Thread, Event
from datetime import datetime, timezone
import time
import sqlite3
from typing import Optional

META_KEYS = ('game_seconds', 'game_running', 'epoch_initialized')


class GameClock:
    """Background thread managing real-time game clock progression.
    
    Counts game seconds and persists to database. Supports pause/resume.
    Automatically recovers from database connection errors.
    
    Attributes:
        conn: Dedicated SQLite connection (check_same_thread=False)
        seconds: Current game time in seconds (read-only property)
        
    Threading:
        - Runs in separate background thread
        - Updates game_seconds in database every second
        - Safe concurrent access with WAL mode
        
    Note:
        Creates dedicated connection from original connection's database file.
        Falls back to original connection if file path unavailable.
    """
    
    def __init__(self, conn: sqlite3.Connection):
        """Initialize game clock with dedicated database connection.
        
        Args:
            conn: SQLite connection to game database
            
        Note:
            - Derives database filename from conn and opens new connection with check_same_thread=False
            - Enables WAL mode for better concurrency
            - Initializes game_seconds, game_running, epoch_initialized in game_meta
            - Falls back to in-memory if file path unavailable
        """
        # Use a dedicated connection that allows cross-thread use.
        # If caller passed a Connection, attempt to derive the filename
        # and open a new connection with check_same_thread=False.
        self._stop = Event()
        self._thread: Optional[Thread] = None
        db_file = None
        try:
            cur = conn.execute("PRAGMA database_list")
            row = cur.fetchone()
            if row and len(row) >= 3:
                db_file = row[2]
        except Exception:
            db_file = None
        # remember original conn/file for reconnect attempts
        self._orig_conn = conn
        self._db_file = db_file
        if not db_file:
            # fallback: assume in-memory or default file; reuse provided conn but allow thread use
            try:
                self.conn = sqlite3.connect(':memory:', check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
            except Exception:
                self.conn = conn
        else:
            self.conn = sqlite3.connect(db_file, check_same_thread=False, timeout=10.0)
            self.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            try:
                self.conn.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass

        # ensure meta keys exist
        self._ensure_meta()
        self._stop_flag = False
        self._immediate_stop = False  # New flag for immediate shutdown

    def _ensure_meta(self):
        """Ensure required game_meta keys exist with default values.
        
        Initializes:
            - game_seconds: 0
            - game_running: 0 (paused)
            - epoch_initialized: current UTC timestamp
            
        Note:
            Called during __init__. Uses INSERT OR REPLACE for idempotency.
        """
        cur = self.conn.execute("SELECT key FROM game_meta")
        existing = {r['key'] for r in cur.fetchall()}
        now = datetime.now(timezone.utc).isoformat()
        if 'game_seconds' not in existing:
            self.conn.execute("INSERT OR REPLACE INTO game_meta(key,value) VALUES(?,?)", ('game_seconds', '0'))
        if 'game_running' not in existing:
            self.conn.execute("INSERT OR REPLACE INTO game_meta(key,value) VALUES(?,?)", ('game_running', '0'))
        if 'epoch_initialized' not in existing:
            self.conn.execute("INSERT OR REPLACE INTO game_meta(key,value) VALUES(?,?)", ('epoch_initialized', now))
        self.conn.commit()

    # persistence helpers
    def _get(self, key: str) -> Optional[str]:
        """Get value from game_meta table with automatic reconnection.
        
        Args:
            key: Meta key to retrieve
            
        Returns:
            String value or None if key doesn't exist
            
        Note:
            - Handles SQLite threading errors with automatic reconnection
            - Uses SQL-escaped literals instead of parameters for thread safety
            - Returns None on error
        """
        try:
            # Some sqlite setups may raise an InterfaceError with param tuples in
            # threaded usage; use a safe escaped literal lookup as a robust fallback.
            k = str(key).replace("'", "''")
            cur = self.conn.execute(f"SELECT value FROM game_meta WHERE key = '{k}'")
            row = cur.fetchone()
            return row['value'] if row else None
        except (sqlite3.InterfaceError, sqlite3.ProgrammingError):
            # Try to reconnect if we have a file path
            try:
                if getattr(self, '_db_file', None):
                    self.conn = sqlite3.connect(self._db_file, check_same_thread=False)
                    self.conn.row_factory = sqlite3.Row
                    cur = self.conn.execute(f"SELECT value FROM game_meta WHERE key = '{k}'")
                    row = cur.fetchone()
                    return row['value'] if row else None
            except Exception:
                return None
            return None

    def _set(self, key: str, value: str):
        """Set value in game_meta table with automatic reconnection and retry.
        
        Args:
            key: Meta key to set
            value: String value to store
            
        Note:
            - Uses INSERT OR REPLACE for upsert behavior
            - Handles database locked errors with 50ms retry
            - Automatically reconnects on interface/programming errors
            - Silently ignores failures after retry
        """
        try:
            k = str(key).replace("'", "''")
            v = str(value).replace("'", "''")
            self.conn.execute(f"INSERT OR REPLACE INTO game_meta(key,value) VALUES('{k}','{v}')")
            self.conn.commit()
        except (sqlite3.InterfaceError, sqlite3.ProgrammingError):
            try:
                if getattr(self, '_db_file', None):
                    self.conn = sqlite3.connect(self._db_file, check_same_thread=False, timeout=10.0)
                    self.conn.row_factory = sqlite3.Row
                    self.conn.execute("PRAGMA journal_mode=WAL")
                    self.conn.execute(f"INSERT OR REPLACE INTO game_meta(key,value) VALUES('{k}','{v}')")
                    self.conn.commit()
            except Exception:
                pass
        except sqlite3.OperationalError as e:
            # Database locked - retry once after short delay
            if 'locked' in str(e).lower():
                try:
                    time.sleep(0.05)
                    self.conn.execute(f"INSERT OR REPLACE INTO game_meta(key,value) VALUES('{k}','{v}')")
                    self.conn.commit()
                except Exception:
                    pass  # Silently ignore if still locked
            else:
                raise

    @property
    def seconds(self) -> int:
        """Get current game time in seconds.
        
        Returns:
            Integer number of seconds elapsed since game start
            
        Note:
            Reads from game_meta table. Handles database errors by returning 0.
        """
        v = self._get('game_seconds')
        return int(v or 0)

    @seconds.setter
    def seconds(self, s: int):
        """Set game time to specific number of seconds.
        
        Args:
            s: Number of seconds to set
            
        Note:
            Updates game_meta table and persists to database.
        """
        self._set('game_seconds', str(int(s)))

    @property
    def running(self) -> bool:
        """Check if game clock is currently ticking.
        
        Returns:
            True if running, False if paused
            
        Note:
            Reads from game_meta table's 'game_running' flag.
        """
        return (self._get('game_running') or '0') == '1'

    @running.setter
    def running(self, val: bool):
        """Set clock running/paused state.
        
        Args:
            val: True to tick, False to pause
            
        Note:
            Persists to database immediately.
        """
        self._set('game_running', '1' if val else '0')

    @property
    def epoch_initialized(self) -> str:
        """UTC timestamp when game clock was first initialized (read-only)."""
        return self._get('epoch_initialized') or ''

    def start(self):
        """Start ticking the clock in background thread (non-blocking).
        
        Note:
            - Creates daemon thread running _run_loop()
            - If thread already alive, just sets running=True (resume)
            - Returns immediately, clock ticks in background
        """
        if self._thread and self._thread.is_alive():
            self.running = True
            return
        self._stop.clear()
        self.running = True
        self._thread = Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def pause(self):
        """Pause clock progression (does not stop thread).
        
        Note:
            Sets running=False. Thread continues but skips tick updates.
            Use resume() or start() to continue ticking.
        """
        self.running = False

    def reset(self):
        """Reset game clock to 0 seconds and update epoch timestamp.
        
        Note:
            - Sets game_seconds to 0
            - Updates epoch_initialized to current UTC time
            - Does not affect running state
        """
        # reset seconds and set new epoch init
        now = datetime.now(timezone.utc).isoformat()
        self.seconds = 0
        self._set('epoch_initialized', now)

    def set_seconds(self, s: int):
        """Set game clock to specific time in seconds.
        
        Args:
            s: Game time in seconds
            
        Note:
            Direct setter for seconds property. Use for time manipulation.
        """
        self.seconds = int(s)

    def stop(self):
        """Stop the clock thread immediately and terminate background loop.
        
        Note:
            - Sets immediate stop flag and event
            - Waits for thread to join (blocks until thread exits)
            - Use pause() if you want to resume later
        """
        self._immediate_stop = True
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.2)  # Wait max 0.2 seconds

    def _run_loop(self):
        """Background thread loop that advances game clock.
        
        Note:
            - Uses time.monotonic() to avoid drift from scheduling variations
            - Advances by whole seconds when elapsed >= 1.0
            - Only ticks when self.running is True
            - Wakes every 0.1s to check stop flag (responsive shutdown)
            - Handles database errors gracefully with fallback to 0
        """
        # Tick in response to real elapsed time using monotonic clock so
        # the clock advances by ~1 second per real second even if the
        # thread scheduling varies. This avoids drifting when the thread
        # wakes earlier/later and improves accuracy.
        last = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            if self.running:
                elapsed = now - last
                if elapsed >= 1.0:
                    # advance by whole seconds elapsed
                    n = int(elapsed)
                    try:
                        cur = int(self._get('game_seconds') or 0)
                    except Exception:
                        cur = 0
                    cur += n
                    self._set('game_seconds', str(cur))
                    last += n
            # wait a short time so stop is responsive
            if self._stop.wait(0.1):
                break

    # formatting helpers
    def format(self) -> str:
        """Format current game time as 'Week W Day D HH:MM:SS'.
        
        Returns:
            Formatted time string
            
        Note:
            - Weeks are 7-day blocks (week 1 starts at day 0)
            - Days are 1-indexed within week (1-7)
            - Time uses 24-hour format with zero-padding
        """
        s = self.seconds
        days = s // 86400
        rem = s % 86400
        hh = rem // 3600
        mm = (rem % 3600) // 60
        ss = rem % 60
        week = days // 7 + 1
        day_of_week = (days % 7) + 1
        return f"Week {week} Day {day_of_week} {hh:02d}:{mm:02d}:{ss:02d}"

    def show(self) -> str:
        """Show detailed clock status including epoch and running state.
        
        Returns:
            String with formatted time, epoch timestamp, and running flag
            
        Example:
            'Week 1 Day 1 00:05:30 (epoch: 2024-01-15T10:30:00+00:00, running=True)'
        """
        return f"{self.format()} (epoch: {self.epoch_initialized}, running={self.running})"