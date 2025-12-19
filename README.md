# KaivosAI

KaivosAI is a minimal mining-game prototype with a Text User Interface (TUI). The game runs in your terminal and displays a live map, object list, game clock, and command input in a single window.

## Run the game

**First, activate the virtual environment:**

```powershell
.venv\Scripts\Activate.ps1
```

Then run the game:

```powershell
python kaivosai.py
```

Or run the package CLI directly:

```powershell
python -m kaivosai.cli
```

The TUI uses [Urwid](https://urwid.org/) to display:
- **Map panel**: live ASCII map with auto-centering and rock-bordered terrain
- **Objects panel**: real-time list of game objects (robots, mines, storage, bases)
- **Clock panel**: Week/Day counter plus HH:MM:SS game time
- **Status panel**: command feedback
- **Command input**: type natural language commands and press Enter

## Natural Language Commands

KaivosAI uses conversational commands that read like spoken language:

### Object Management
- `create robot at 5 7` — create a robot at position (5,7)
- `add mine at 3 4` — add a mine at position (3,4)
- `remove at 5 7` — remove whatever is at position (5,7)
- `delete 12` — remove object with ID 12
- `move 3 4 to 7 7` — move object from (3,4) to (7,7)
- `what at 8 8` — inspect what's at position (8,8)

### Robot Control
- `robot 3 go to 10 10` — command robot #3 to move to (10,10)
- `bot 5 goto 8 8` — alternative syntax for robot movement

### Viewing
- `list` or `objects` — show all objects (robots, mines, storage, bases)
- `show` or `map` — display the ASCII map

### Terrain & Setup
- `generate terrain` — create bordered map with natural rock formations
- `generate terrain 0.08 5` — custom density (0.08) and cluster size (5)
- `demo` — add demo objects for testing

### Time Control
- `pause` or `stop` — pause game clock
- `resume` or `start` — resume game clock
- `time` — show current game time
- `reset time` — reset clock to zero

### Game Control
- `reset` — clear all objects and reset clock
- `help` or `?` — show command list
- `quit` or `exit` — exit game (or press ESC)

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
- Command: `robot 3 go to 10 10`
- Robots automatically find paths around rocks and other objects
- Movement happens in real-time (one step every 0.5 seconds)
- Blocked paths are recalculated automatically

### Persistent Game Clock
The game clock runs in the background and persists across sessions:
- Shows as **W{week} D{day} HH:MM:SS** format
- Continues even when you quit and restart
- Control with `pause`, `resume`, `reset time` commands

## Persistence

Game state is persisted in `game.db` (SQLite). Objects added/removed/moved are saved automatically. The game clock state is also saved and restored between sessions.

## Migrations

Deduplicate and migrate `game.db` (creates backup `game.db.bak`):

```powershell
python -m kaivosai.migrations
```

## Development tools

### Task manager

A small CLI task manager (`taskmanager.py`) tracks TODOs while developing. Tasks persist in `tasks.db`. Intended as developer convenience — not part of gameplay.

### Committing & pushing

Helper script `commit_and_push.ps1` automates git commits. If PowerShell blocks, run git commands directly (see script for steps).

### Dependencies

Install Urwid for TUI support:

```powershell
python -m pip install urwid
```

If Urwid is not available, the game falls back to a basic REPL mode with the same natural language commands.
