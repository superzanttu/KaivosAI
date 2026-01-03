# KaivosAI Coding Agent Instructions

All comments, docstrings, and documentation must be written in **Finnish**. Translate all comments to Finnish.

## Architecture Overview

KaivosAI is a mining-game simulation with per-robot RoboBASIC VM execution. Three critical architectural decisions:

1. **Per-Robot VM Isolation** (`robobasic.py`): Each Robot gets its own RoboBASICVM instance via `__post_init__()`. Robots are completely isolated - no shared state between VMs. This is NOT a global singleton.

2. **Tick-Based Execution** (`gameloop.py`): Everything happens in discrete game ticks:
   - GameLoop.process_tick() calls object.on_tick() for all game objects
   - Robot.on_tick() → self.vm.tick(game_map) executes one RoboBASIC instruction per tick
   - Background processes (LOAD/UNLOAD) advance 1 material unit per tick via vm._process_transfers()

3. **Spatial Authority** (`map.py`): Map.cells[Position] is the authoritative spatial index. All position changes flow through Map.add_object() and internal _move_robot() to keep Map.cells synchronized.

## RoboBASIC VM Details

The VM is a tick-driven interpreter (lines 266-520 in robobasic.py):
- **Parser phase**: RoboBASICParser converts source code → ParsedProgram (instructions + label map)
- **Load phase**: VM loads program into VMState (sets execution_mode=STOP)
- **Execution phase**: vm.tick(game_map) executes instructions until 1 tick consumed
  - Nula-tikki commands: GOTO, IF (when jumping), LABEL, NOP (skip to next instruction)
  - One-tikki commands: MOVE, LOAD, UNLOAD, SET TARGET, WAIT, PRINT (consume 1 tick)
  - Material transfers happen in _process_transfers() before instruction execution
- **Robot state machine**: IDLE→MOVING→TARGET (or BLOCKED), with LOADING/UNLOADING as parallel states

16 command types defined in CommandType enum. Label syntax: `:LABELNAME` (uppercase only).

## Database & Persistence Pattern

SQLite uses WAL mode (pragma journal_mode=WAL) for concurrency. Batch operations pattern:
```python
if self.conn and objects_list:
    try:
        self.conn.execute("BEGIN")
        for obj in objects_list:
            persist_object(self.conn, obj, commit=False)
        self.conn.commit()
    except Exception:
        self.conn.rollback()
```
Used in Map.save_to_db(), add_initial_buildings(), generate_border_rocks(). Never call persist_object() individually in loops - always batch in transactions.

## Project Conventions

- **Version tracking**: VERSION in version.py, flag_new_version.lck signals new version, commit_message.txt is append-only changelog
- **Sphinx documentation**: Docstrings generate HTML via `./update_docs.ps1` (autodoc + napoleon for Google-style docstrings)
- **Dependencies**: `requirements.txt` (root) for runtime, `docs/requirements.txt` (Sphinx)
- **Finnish comments only**: All inline comments, docstrings, variable names in docstrings must be Finnish
- **RoboBASIC syntax**: Commands UPPERCASE, labels `:UPPERCASE`, literals in PRINT/ERROR use Finnish text

## Critical Workflows

| Task | Command |
|------|---------|
| Run game | `.\run.ps1` |
| Build docs | `.\update_docs.ps1` (generates docs/_build/html/) |
| Commit changes | `.\commit_and_push.ps1` |
| Install deps | `python -m pip install -r requirements.txt` |
| Test imports | `python -c "import map; import kaivosai"` |

## Key Files & Their Roles

- **robobasic.py** (1300+ lines): RoboBASICParser + RoboBASICVM with full docstring docs of VM operation
- **map.py** (665 lines): Map-based world, object spatial management, batch persistence
- **models.py** (280 lines): Game entities (Robot, Mine, Storage, Base, Rock) with Robot.vm creation
- **gameloop.py** (120 lines): GameLoop.process_tick() orchestrates all game object ticks
- **database.py** (500+ lines): SQLite operations, NOT persist_objects_batch (doesn't exist - use transaction loop)
- **kaivosai.py** (700+ lines): Textual TUI, NOT recommended for AI changes (complex widget management)

## Integration Points

- **Robot initialization**: Create Robot(pos, program_text) → __post_init__() creates self.vm = RoboBASICVM(self)
- **Game execution**: GameLoop.process_tick() → calls obj.on_tick() for all objects including robots
- **Execution result**: vm.tick(game_map) returns error message string or None (used for ERROR state)
- **Material transfers**: Robot material transfers happen in vm._process_transfers() (1 unit/tick), not in database
- **Map queries**: Always use Map.in_bounds(), is_occupied(), get_viewport_objects() - never access Map.cells directly

## Common Mistakes to Avoid

1. **Using global VM**: There is NO global VM - each robot has its own. Never create RoboBASICVM outside robot.vm
2. **Direct cell manipulation**: Never do `map.cells[pos] = obj` directly - use Map.add_object() or _move_robot()
3. **Non-transactional persist**: Don't call persist_object() in a loop without BEGIN/COMMIT wrapper
4. **Ignoring tick consumption**: Commands return 'tick', 'continue', 'jump', 'end', 'error' - these determine next PC and whether to stop executing this tick
5. **English comments**: All project comments are Finnish - translate required
6. **Material capacity assumptions**: Don't hardcode 10 units - use object.material_capacity (varies by object type)
