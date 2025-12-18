"""KaivosAI public API.

Expose a small, explicit surface for consumers. `_legacy.py` remains
in the package for compatibility but is not re-exported by default.
"""
from .db import get_game_conn, init_game_db
from .map import Map
from .cli import run_demo, repl
from .viewer import run_viewer
from .migrations import migrate_deduplicate

__all__ = [
	'get_game_conn',
	'init_game_db',
	'Map',
	'run_demo',
	'repl',
	'run_viewer',
	'migrate_deduplicate',
]
