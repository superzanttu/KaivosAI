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
- **Map panel**: live ASCII map with auto-centering
- **Objects panel**: real-time list of all game objects
- **Clock panel**: block-digit HH:MM:SS plus Week/Day summary (blinking colon)
- **Status panel**: command feedback
- **Command input**: type commands and press Enter

## Commands

All commands work in the TUI command input:

- `add TYPE [ID] X Y` — add object (ID optional; omitted = auto-assigned)
- `remove X Y` — remove object at position or `remove ID` for by-id removal
- `move X1 Y1 X2 Y2` — move an object
- `get X Y` — show object at a position
- `goto ROBOT_ID X Y` — command robot to move to target
- `time show|pause|resume|reset|set <seconds>` — control game clock
- `reset` — clear all objects and reset clock
- `demo` — add demo objects with IDs 1-5 (mine, storage, base, robot, rock)
- `help` — show command list
- `quit` or `ESC` — exit

## Game objects

- `Robot` (R) — autonomous agent
- `Mine` (M) — resource source
- `Storage` (S) — resource storage
- `Base` (B) — home base
- `Rock` (#) — impassable obstacle

## Persistence

Game state is persisted in `game.db` (SQLite). Objects added/removed/moved are saved automatically.

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
