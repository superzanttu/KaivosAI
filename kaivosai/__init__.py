"""KaivosAI public API.

Expose a small, explicit surface for consumers. `_legacy.py` remains
in the package for compatibility but is not re-exported by default.
"""

VERSION = "0.18.0"

from .db import get_game_conn, init_game_db, load_objects_from_db
from .map import Map
from .textual_cli import run_textual_tui
from .migrations import migrate_deduplicate
from .models import Robot, Mine, Storage, Base, Rock
from .models import create_object
from .clock import GameClock
from .exceptions import (
    GameError, MapError, DatabaseError, CommandError, 
    RobotError, ValidationError
)


def run_demo(db_path: str = "databases/game.db"):
    """Compatibility wrapper that launches the Textual TUI.
    
    Args:
        db_path: Path to SQLite database file (default: databases/game.db)
    """
    run_textual_tui(db_path)

__all__ = [
	'VERSION',
	'get_game_conn',
	'init_game_db',
	'Map',
	'run_demo',
	'run_textual_tui',
	'migrate_deduplicate',
	'load_objects_from_db',
	'Robot',
	'Mine',
	'Storage',
	'Base',
	'Rock',
	'create_object',
	'GameClock',
	'GameError',
	'MapError',
	'DatabaseError',
	'CommandError',
	'RobotError',
	'ValidationError',
]
