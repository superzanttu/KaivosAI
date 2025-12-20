## KaivosAI — Copilot / Agent Instructions

Focused guidance for AI coding agents working on this mining game TUI project.

## 1. Architecture Overview

**KaivosAI** is a terminal-based mining simulation with persistent state, real-time clock, and material production/consumption.

Core components:
- [kaivosai/db.py](kaivosai/db.py) — SQLite persistence: `init_game_db()`, `persist_object()`, `load_objects_from_db()`, `game_meta` table; databases stored in `databases/` directory
- [kaivosai/models.py](kaivosai/models.py) — Game objects as dataclasses: `Robot`, `Mine`, `Storage`, `Base`, `Rock`, `create_object()` factory
- [kaivosai/map.py](kaivosai/map.py) — In-memory `Map` class: dict of `(x,y)->object`, syncs to DB, pathfinding, production/consumption ticks
- [kaivosai/cli.py](kaivosai/cli.py) — Urwid TUI: natural language command processor, colored map display, object list, clock display
- [kaivosai/clock.py](kaivosai/clock.py) — Background `GameClock` thread, persists `game_seconds` in `game_meta` table
- [kaivosai/viewer.py](kaivosai/viewer.py) — Read-only Urwid viewer polling `databases/game.db`
- [kaivosai/migrations.py](kaivosai/migrations.py) — Safe schema migrations with backups

Entry point: `kaivosai.py` calls `run_demo()` → starts Urwid TUI with 30x30 map

Database files stored in `databases/` directory (auto-created):
- `databases/game.db` — main game state (objects, clock)
- `databases/game.db.bak` — backup created by migrations
- `databases/game.db-shm`, `databases/game.db-wal` — SQLite WAL files

## 2. Material System (v0.2.0+)

**Key mechanics:**
- Mines: produce 1 material/10s (max capacity 10, stops when full)
- Storage: holds up to 20 materials
- Robots: carry up to 5 materials
- Bases: consume 1 material/10s if available

**Implementation:**
- Production/consumption: `Map.tick_production(game_seconds)` called every 0.5s from `refresh_display()`
- Objects track `stored`, `capacity`, `last_production_time`, `last_consumption_time`
- Backward compatibility: missing fields auto-initialized in `produce()`/`consume()` methods

## 3. Critical Patterns

**Coordinate uniqueness:**
- `(x,y)` is the canonical key; DB has `UNIQUE(x,y)` constraint
- `persist_object()` uses `ON CONFLICT(x,y) DO UPDATE` UPSERT
- Fallback for old DBs: catches `OperationalError` and does delete+insert — **preserve this**

**Threading:**
- `GameClock` runs in background thread with its own `check_same_thread=False` connection
- Never share main thread's DB connection with clock thread

**Map operations:**
- `Map.get(pos)` returns object at position (not `get_object()`)
- `Map.remove_object()` accepts `(x,y)` tuple OR integer `id`
- Viewer is read-only — never writes to DB

## 4. Developer Workflows

```powershell
# Run game (requires urwid)
python kaivosai.py

# Run viewer (separate window)
python -m kaivosai.viewer

# Run tests
python -m unittest
python -m unittest tests.test_persistence

# Run migration (creates databases/game.db.bak)
python -m kaivosai.migrations

# Commit workflow (reads commit_message.txt, then deletes it)
.\commit_and_push.ps1

# Reset game (remove databases directory)
Remove-Item -Recurse databases/
```

## 5. Urwid TUI Details

**Color palette** (in `run_urwid_tui()`):
- Robot: light cyan, Mine: yellow, Storage: light green, Base: light magenta, Rock: dark gray

**Map rendering:**
- `build_map_display()` returns Urwid markup list (not string) for colored output
- Display limit: 120x60 (to fit 30x30 map with margins)
- Auto-centers on objects; falls back to (0,9)x(0,9) if map empty

**Command processing:**
- Natural language parser in `process_command()` using `shlex.split()`
- Status shows: `> command\nresult` (command echo + output)
- Commands: create, remove, move, robot go, list, show, generate terrain, demo, pause/resume, reset, version, help, quit

## 6. Adding New Features

**New game object type:**
1. Add dataclass in [kaivosai/models.py](kaivosai/models.py)
2. Update `create_object()` factory
3. Add DB field if needed in [kaivosai/db.py](kaivosai/db.py) `init_game_db()`
4. Add color to palette in [kaivosai/cli.py](kaivosai/cli.py) `run_urwid_tui()`
5. Add rendering case in `build_map_display()`

**New command:**
1. Add parser case in `process_command()` in [kaivosai/cli.py](kaivosai/cli.py)
2. Update help text in `help` command branch
3. Return status string (will show as `> command\nresult`)

**DB schema change:**
1. Add migration function in [kaivosai/migrations.py](kaivosai/migrations.py)
2. Update `init_game_db()` in [kaivosai/db.py](kaivosai/db.py)
3. Update `persist_object()` if adding fields
4. Test with old DB file to verify backward compatibility

## 7. Version & Instructions

- Version tracked in `kaivosai.VERSION` (currently "0.2.0")
- Always update `VERSION` in [kaivosai/\_\_init\_\_.py](kaivosai/__init__.py) for significant changes
- Update `commit_message.txt` immediately after code changes (auto-commit helper reads this)

## 8. Testing & Safety

- Run `tests/test_persistence.py` after any DB or Map changes
- Tests cover: persist, move, delete-by-id, migration deduplication
- **Never remove** delete+insert fallback in `persist_object()` without migration + test verification
- Reset game for clean testing: `reset` command OR `Remove-Item -Recurse databases/`
- Database files in `databases/` directory are gitignored

## 9. Common Gotchas

- Demo objects spawn randomly in 30x30 area (uses `time.time() * 1e6 + os.urandom(4)` seed)
- Terrain generation uses `random` module — seed before calling `generate_full_terrain()`
- Map size is 30x30 (was 50x50 in early versions)
- Object list shows: `ID NAME (X,Y) inv:X/Y` (robots) or `mat:X/Y` (mines/storage/bases)
- Clock display: `W1 D1  HH:MM:SS` format

Need examples for: pathfinding patterns, robot movement commands, or specific test scenarios? Ask for details.
