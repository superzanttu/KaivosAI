# KaivosAI

KaivosAI is a minimal mining-game prototype with a Text User Interface (TUI). The game runs in your terminal and displays a live map, object list, game clock, and command input in a single window.

## Run the game

**Quick start (Windows PowerShell):**

```powershell
.\test.ps1
```

This launches KaivosAI in a separate window. The script automatically:
- Activates the virtual environment
- Checks dependencies
- Starts the game

**Manual launch:**

First, activate the virtual environment:

```powershell
.venv\Scripts\Activate.ps1
```

Then run the game:

```powershell
python kaivosai.py
```

**Other platforms:**

- **Linux/macOS/WSL:** `./run.sh`
- **Windows CMD:** `run.bat`

The TUI uses [Textual](https://textual.textualize.io/) framework to display:
- **Map panel**: live ASCII map with auto-centering and rock-bordered terrain
- **Objects panel**: real-time list of game objects (robots, mines, storage, bases)
- **Clock panel**: Week/Day counter plus HH:MM:SS game time
- **Status panel**: command feedback
- **Command input**: type natural language commands and press Enter

## Commands Overview

KaivosAI accepts natural-language style commands. Below are the supported forms used by the current CLI.

### Object Management
- `create TYPE X Y` — create object of type at position (X,Y); types: robot, mine, storage, base, rock
- `delete at X Y` — remove whatever is at position (X,Y)
- `delete id N` — remove object with ID N
- `delete X Y` — remove by coordinates (shorthand)
- `move X Y to X2 Y2` — move object instantly from (X,Y) to (X2,Y2)
- `inspect X Y` — show what is at position (X,Y)

### Robot Control
- `robot ID goto X Y [distance N]` — move robot to coordinates, optionally stopping N cells away
- `robot ID goto OBJ_ID [distance N]` — move adjacent to object by ID (defaults to 1 cell away if no distance)
- `robot ID load [N]` — start loading N materials from an adjacent source (Mine/Storage/Base/Robot); if omitted, loads until full
- `robot ID unload [N]` — start unloading N materials to an adjacent destination (Storage/Base/Robot); if omitted, unloads all
- `robot ID code` — open RoboBASIC editor for the robot (aliases: `r ID c`, `code`, `prg`, `prog`)
- `robot ID start` — start executing the robot code (aliases: `r ID s`, `start`, `run`, `execute`)
- `robot ID pause` — pause robot code execution (aliases: `r ID p`, `pause`, `stop`, `halt`)
- Aliases: `r`, `bot`, `go`, `move`, `g`, `take`, `drop` (plus context-aware `c`/`s`/`p` after `robot ID`)

### Viewing
- `map show` — see map panel
- `map list` — see objects panel
- Top-level aliases: `show` → `map`, `ls/objects` → `list` (redirects to panels)

### Terrain & Setup
- `map terrain [density] [cluster]` — generate terrain with border + clusters (density 0.0–1.0, cluster ≥1)
- `map demo` — add demo objects at random free positions
- `map reset` — clear map and reset clock

### Time Control
- `pause` — pause game clock
- `resume` — resume game clock
- `system pause` / `system resume` — clock control via system

### Game Control
- `map reset` — clear all objects and reset clock
- `help` or `system help` — show command list
- `version` or `system version` — show version
- `quit` or `system quit` — exit game

## Game objects

- `Robot` (R) — autonomous agent that can be commanded to move
- `Mine` (M) — resource source
- `Storage` (S) — resource storage
- `Base` (B) — home base
- `Rock` (#) — impassable obstacle (forms map borders and terrain)

## Features

### Terrain Generation
On first launch, the game automatically generates:
- **Border rocks**: Impassable walls around the map edges
- **Interior rocks**: Natural-looking rock clusters for obstacles

Use `generate terrain` to regenerate terrain with default settings, or customize:
- **Density** (0.0-1.0): probability of rock cluster formation (default: 0.05)
- **Cluster size** (1+): average rocks per cluster (default: 3)

Example: `generate terrain 0.08 5` creates denser terrain with larger clusters.

### Robot Movement
Robots use pathfinding to navigate around obstacles:
- Command: `robot 3 goto 10 10`
- Robots automatically find paths around rocks and other objects
- Movement happens in real-time
- Blocked paths are recalculated automatically

### Persistent Game Clock
The game clock runs in the background and persists across sessions:
- Shows as **W{week} D{day} HH:MM:SS** format
- Continues even when you quit and restart
- Control with `pause`, `resume`, `reset time` commands

## Persistence

Game state is persisted in `databases/game.db` (SQLite). The `databases/` directory is created automatically on first run. Objects added/removed/moved are saved automatically. The game clock state is also saved and restored between sessions.

## Migrations

Deduplicate and migrate `databases/game.db` (creates backup `databases/game.db.bak`):

```powershell
python -m kaivosai.migrations
```

## Development & Testing

### Task manager

A small CLI task manager (`taskmanager.py`) tracks TODOs while developing. Tasks persist in `databases/tasks.db`. Intended as developer convenience — not part of gameplay.

### Committing & pushing

Helper script `commit_and_push.ps1` automates git commits. If PowerShell blocks, run git commands directly (see script for steps).

### Dependencies

Install Textual for TUI support:

```powershell
python -m pip install textual
```

Textual is required to run the game.

### Testing & Coverage

Run the test suite and coverage report:

```powershell
coverage run -m unittest discover -s tests -p "test_*.py"
coverage report -m
```

Coverage configuration is managed in [.coveragerc](.coveragerc). The report is restricted to core API files and enforces 100% via `fail_under=100`. UI/TUI and thread-bound modules are omitted from the report for practicality.

### Version

Current version: see [kaivosai/__init__.py](kaivosai/__init__.py). After changes, update VERSION, append a line to [commit_message.txt](commit_message.txt), and recreate [flag_new_version.lck](flag_new_version.lck) to signal reload.
