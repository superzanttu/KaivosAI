"""Game loop engine for KaivosAI - processes game events at fixed tick rate."""

import asyncio
from datetime import datetime
from typing import Optional
import database


class GameLoop:
    """Manages background game state updates and event processing."""
    
    def __init__(self, app, dbconn, tick_rate: float = 1.0):
        """
        Initialize the game loop.
        
        Args:
            app: Reference to the Textual app instance
            dbconn: Database connection for persisting game state
            tick_rate: Seconds between game ticks (default 1.0 = 1 per second)
        """
        self.app = app
        self.dbconn = dbconn
        self.tick_rate = tick_rate
        self.running = False
        self.paused = False
        self.tick_count = 0
        self.last_tick_time = datetime.now()
    
    async def run(self):
        """Main game loop - runs independently in background."""
        self.running = True
        while self.running:
            if not self.paused:
                await self.process_tick()
            await asyncio.sleep(self.tick_rate)
    
    async def process_tick(self):
        """Process one game tick - called every tick_rate seconds."""
        try:
            self.tick_count += 1
            self.last_tick_time = datetime.now()
            
            # Update game logic
            await self._update_robots()
            await self._update_mining()
            await self._process_pending_commands()
            await self._check_resource_transfers()
            
            # Log tick event (less frequently to avoid spam)
            if self.tick_count % 10 == 0:
                database.log_event(
                    self.dbconn,
                    "game_tick",
                    f"Game tick {self.tick_count}"
                )
            
            # Notify UI to refresh
            await self.app.update_game_ui()
            
        except Exception as e:
            database.log_event(
                self.dbconn,
                "game_error",
                f"Game tick error: {str(e)}"
            )
    
    async def _update_robots(self):
        """Update robot positions and states."""
        # TODO: Implement robot movement logic
        # - Process waypoints
        # - Update positions
        # - Handle collisions
        pass
    
    async def _update_mining(self):
        """Update mining operations."""
        # TODO: Implement mining logic
        # - Extract resources
        # - Update mine states
        # - Handle full storage
        pass
    
    async def _process_pending_commands(self):
        """Process queued user commands."""
        # TODO: Get commands from queue and apply them
        pass
    
    async def _check_resource_transfers(self):
        """Handle resource transfers between entities."""
        # TODO: Implement transfer logic
        # - Robot to storage deposits
        # - Base to robot refueling
        pass
    
    def pause(self):
        """Pause the game loop."""
        self.paused = True
        database.log_event(self.dbconn, "game_paused", "Game paused")
    
    def resume(self):
        """Resume the game loop."""
        self.paused = False
        database.log_event(self.dbconn, "game_resumed", "Game resumed")
    
    def stop(self):
        """Stop the game loop gracefully."""
        self.running = False
        database.log_event(
            self.dbconn,
            "game_stop",
            f"Game stopped after {self.tick_count} ticks"
        )
