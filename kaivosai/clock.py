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
        if not db_file:
            # fallback: assume in-memory or default file; reuse provided conn but allow thread use
            try:
                self.conn = sqlite3.connect(':memory:', check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
            except Exception:
                self.conn = conn
        else:
            self.conn = sqlite3.connect(db_file, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

        # ensure meta keys exist
        self._ensure_meta()

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
        cur = self.conn.execute("SELECT value FROM game_meta WHERE key = ?", (key,))
        row = cur.fetchone()
        return row['value'] if row else None

    def _set(self, key: str, value: str):
        self.conn.execute("INSERT OR REPLACE INTO game_meta(key,value) VALUES(?,?)", (key, str(value)))
        self.conn.commit()

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
        self.running = False
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _run_loop(self):
        # Tick once per real second while running.
        while not self._stop.is_set():
            if self.running:
                # increment by 1 second
                try:
                    cur = int(self._get('game_seconds') or 0)
                except Exception:
                    cur = 0
                cur += 1
                self._set('game_seconds', str(cur))
            # sleep a second in small increments to be responsive to stop
            for _ in range(10):
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