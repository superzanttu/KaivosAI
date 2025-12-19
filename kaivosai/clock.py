"""Game clock for KaivosAI.

Provides a persistent, ticking game clock stored in `game_meta`.
Clock counts seconds; weeks are 7-day blocks. Time format shown as
"Week W Day D HH:MM:SS". The clock persists `game_seconds`,
`game_running` and `epoch_initialized` in `game_meta`.
"""
from __future__ import annotations
from threading import Thread, Event
from datetime import datetime, timezone
import time
import sqlite3
from typing import Optional

META_KEYS = ('game_seconds', 'game_running', 'epoch_initialized')


class GameClock:
    def __init__(self, conn: sqlite3.Connection):
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
        v = self._get('game_seconds')
        return int(v or 0)

    @seconds.setter
    def seconds(self, s: int):
        self._set('game_seconds', str(int(s)))

    @property
    def running(self) -> bool:
        return (self._get('game_running') or '0') == '1'

    @running.setter
    def running(self, val: bool):
        self._set('game_running', '1' if val else '0')

    @property
    def epoch_initialized(self) -> str:
        return self._get('epoch_initialized') or ''

    def start(self):
        """Start ticking the clock in background (non-blocking)."""
        if self._thread and self._thread.is_alive():
            self.running = True
            return
        self._stop.clear()
        self.running = True
        self._thread = Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def pause(self):
        self.running = False

    def reset(self):
        # reset seconds and set new epoch init
        now = datetime.now(timezone.utc).isoformat()
        self.seconds = 0
        self._set('epoch_initialized', now)

    def set_seconds(self, s: int):
        self.seconds = int(s)

    def stop(self):
        """Stop the clock thread immediately."""
        self._immediate_stop = True
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.2)  # Wait max 0.2 seconds

    def _run_loop(self):
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
        return f"{self.format()} (epoch: {self.epoch_initialized}, running={self.running})"