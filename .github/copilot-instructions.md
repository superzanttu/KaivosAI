## KaivosAI — Copilot / Agent Instructions

Short, actionable guidance for AI coding agents working on this repository.

Overview
- `kaivosai/` is the game package; `kaivosai.py` is the small top-level runner that calls `run_demo()`.
- Core modules:
  - `kaivosai/db.py` — DB schema, `init_game_db()`, `persist_object()`, `load_objects_from_db()`, and `game_meta` table.
  - `kaivosai/map.py` — `Map` class: in-memory (x,y)->object; calls DB helpers when `conn` is provided.
  - `kaivosai/models.py` — dataclasses and `create_object()` factory.
  - `kaivosai/cli.py` — REPL, `run_demo()`, and `time` commands; starts/stops `GameClock`.
  - `kaivosai/clock.py` — background `GameClock`, persists `game_seconds` in `game_meta`; uses thread-safe DB connection.
  - `kaivosai/migrations.py` — safe dedupe migration (backs up DB, creates UNIQUE(x,y), swaps tables).

Key patterns & constraints
- Coordinates `(x,y)` are the canonical uniqueness key. `persist_object()` prefers `ON CONFLICT(x,y)` UPSERT but falls back to delete+insert for older DBs — preserve that fallback unless a migration is added and verified.
- `GameClock` runs in a background thread and opens its own SQLite connection with `check_same_thread=False` (don’t reuse main-thread connection from the thread).
- `Map.remove_object()` accepts either a position tuple `(x,y)` or an integer `id`. CLI `remove` supports both.
- Viewer reads from `game.db` only and should not perform writes.

Developer workflows (quick)
- Run demo: `python kaivosai.py` or `python -m kaivosai.cli`.
- Run viewer: `python -m kaivosai.viewer`.
- Run migration: `python -m kaivosai.migrations` (creates `game.db.bak`).
- Run tests: `python -m unittest` or `python -m unittest tests.test_persistence`.
- Commit helper: `commit_and_push.ps1` reads `commit_message.txt` (if present) then deletes it after a successful commit.

Where to look when changing things
- DB/persistence changes: `kaivosai/db.py` and `kaivosai/migrations.py` (update tests in `tests/test_persistence.py`).
- Map/behaviour/CLI: `kaivosai/map.py`, `kaivosai/models.py`, `kaivosai/cli.py`.
- Clock/timing: `kaivosai/clock.py` and `cli.run_demo()` (clock lifecycle handling).

Examples & snippets
- Load persisted rows: see `kaivosai/map.py` loader loop using `create_object(type, id=..., pos=(x,y), ...)`.
- Persist: `persist_object(conn, obj)` — may assign `obj.id`.
- Safe migrate pattern: backup file, create `_new` table with UNIQUE(x,y), insert one row per (x,y) (keep max id), drop old, rename new (see `kaivosai/migrations.py`).

Testing & safety
- Always run `tests/test_persistence.py` after DB or CLI changes. Tests cover persisting, moves, delete-by-id, and migration deduplication.
- Do not remove delete+insert fallback in `persist_object` without adding/validating the migration and updating tests.

If you want detailed examples (sample `game_meta` rows, CI/action workflow, or test templates for clock behavior), tell me which area to expand.
## KaivosAI — Copilot / Agent Instructions

This file gives focused, repository-specific guidance for AI coding agents so they can be productive quickly.

1. Big picture
- Project: a minimal mining game implemented as a Python package `kaivosai` with a small top-level runner `kaivosai.py`.
- Major components:
  - [kaivosai/db.py](kaivosai/db.py): SQLite helpers, `init_game_db`, `persist_object`, `load_objects_from_db`, `game_meta` table.
  - [kaivosai/models.py](kaivosai/models.py): dataclass definitions for `Robot`, `Mine`, `Storage`, `Base`, `Rock` and `create_object()`.
  - [kaivosai/map.py](kaivosai/map.py): in-memory `Map` class (dict of `(x,y)->object`) that syncs with the DB when `conn` is provided.
  - [kaivosai/cli.py](kaivosai/cli.py): interactive REPL and `run_demo()`; responsible for starting the game clock.
  - [kaivosai/clock.py](kaivosai/clock.py): persistent background `GameClock` storing `game_seconds` in `game_meta`.
  - [kaivosai/migrations.py](kaivosai/migrations.py): safe deduplication migration that backs up `game.db` and creates UNIQUE(x,y).

2. Data flows & boundaries
- Map objects are authoritative in-memory during a session; persistence occurs via `persist_object` calls in `Map.add_object`/`move_object` and `delete_object_db` on removal.
- The DB schema now includes `game_meta` for small persistent settings (clock, epoch).
- The viewer (`kaivosai.viewer`) reads directly from the DB and should not try to mutate state.

3. Developer workflows & commands
- Run demo (interactive REPL): `python kaivosai.py` (or `python -m kaivosai.cli` to run CLI module).
- Run unit tests: `python -m unittest` (tests are under `tests/`).
- Run migration (creates `game.db.bak`): `python -m kaivosai.migrations`
- Commit helper (PowerShell): run `.
elease_and_push.ps1` (or use `commit_and_push.ps1`). If PowerShell blocks, run Git commands directly.

4. Project-specific conventions and gotchas
- DB uniqueness: the intended canonical rule is UNIQUE(x,y). Migration enforces this, but code supports fallback (delete+insert) for older DBs.
- `persist_object` uses UPSERT by coordinates when the DB supports UNIQUE(x,y). For older DBs the code catches OperationalError and falls back — when editing persistence, preserve this dual-mode behavior.
- The `GameClock` runs in a background thread and opens its own SQLite connection with `check_same_thread=False`. Be careful when modifying clock persistence or threading code.
- `Map.remove_object` accepts either `(x,y)` or an integer `id`. CLI `remove` was updated accordingly.

5. Tests and guarantees
- Existing unit tests in `tests/test_persistence.py` cover persistence, moving, removal-by-id, and migration deduplication. Run them after changes.

6. Integration points
- Expose public APIs in [kaivosai/__init__.py](kaivosai/__init__.py): `Map`, `run_demo`, `run_viewer`, `migrate_deduplicate`, `get_game_conn`, `init_game_db`.
- Viewer reads the DB directly — if adding write logic, prefer using `Map` methods.

7. Common PR tasks for agents
- When changing DB schema:
  - Add a safe migration under [kaivosai/migrations.py](kaivosai/migrations.py).
  - Ensure `init_game_db` keeps backward compatibility and that `persist_object` falls back gracefully.
- When changing REPL/CLI commands: update `show_help()` in [kaivosai/cli.py](kaivosai/cli.py) and add tests if logic is non-trivial.

8. Quick code pointers (examples)
- To load persisted objects: `rows = load_objects_from_db(conn)` then `create_object(row['type'], id=row['id'], name=row['name'], pos=(row['x'],row['y']), capacity=row['capacity'], durability=row['durability'])` (see [kaivosai/map.py](kaivosai/map.py)).
- To persist an object use: `persist_object(conn, obj)`; it assigns `obj.id` when needed.

9. Safety & testing priorities
- Preserve existing behavior: do not remove fallback delete+insert in `persist_object` unless migration is applied and verified.
- Add tests for DB migrations and clock behavior when modifying those modules.

If anything here is unclear or you'd like more examples (e.g. expected DB contents after operations, or a recommended test matrix), tell me which area to expand.