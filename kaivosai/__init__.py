"""KaivosAI public API.

Expose a small, explicit surface for consumers. `_legacy.py` remains
in the package for compatibility but is not re-exported by default.
"""

VERSION = "0.4.2"

from .db import get_game_conn, init_game_db, load_objects_from_db
from .map import Map
from .cli import run_demo
from .migrations import migrate_deduplicate
from .models import Robot, Mine, Storage, Base, Rock
from .models import create_object
from .clock import GameClock

__all__ = [
	'VERSION',
	'get_game_conn',
	'init_game_db',
	'Map',
	'run_demo',
	'migrate_deduplicate',
	'load_objects_from_db',
	'Robot',
	'Mine',
	'Storage',
	'Base',
	'Rock',
	'create_object',
	'GameClock',
]
