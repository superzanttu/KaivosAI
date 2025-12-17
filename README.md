# KaivosAI (primary project)

KaivosAI is a minimal mining-game prototype. The repository includes a small interactive demo that runs a persistent map, game objects, and a REPL for manual testing and development.

Run the game demo:

```powershell
python kaivosai.py
```

Map & REPL basics

- The demo map defaults to 50x50.
- Objects: `Robot`, `Mine`, `Storage`, `Base`, and impassable `Rock`.
- Map REPL commands:
	- `add TYPE ID X Y` : add object (TYPE: `robot`, `mine`, `storage`, `base`, `rock`)
	- `remove X Y` : remove object at position
	- `move X1 Y1 X2 Y2` : move an object
	- `list` : list all objects on the map
	- `get X Y` : show object at a position
	- `show [minx maxx miny maxy]` : ASCII map (auto-bounds when omitted)

Persistence

- Game state is persisted in `game.db` (SQLite). Objects added/removed/moved in the REPL are saved automatically when a DB connection is used.

The rest of this repository contains helper tooling useful when developing the game.

**KaivosAI — Mining Game**

A minimal game/demo for KaivosAI. The game objects and a small interactive map live in `kaivosai.py`.

- Run the demo (starts REPL):

```powershell
python kaivosai.py
```

- Map REPL commands (in `kaivosai.py`):
	- `add TYPE ID X Y` : add object (TYPE: `robot`, `mine`, `storage`, `base`, `rock`)
	- `remove X Y` : remove object at position
	- `move X1 Y1 X2 Y2` : move an object
	- `list` : list all objects on the map
	- `get X Y` : show object at a position
	- `show [minx maxx miny maxy]` : ASCII map (auto-bounds when omitted)

The demo uses `game.db` (SQLite) to persist all game objects and their state.

Helper tools

Task manager (developer helper): a small CLI task manager remains in `taskmanager.py` to track TODOs while developing the game. Tasks persist in `tasks.db` (SQLite). It is intended as a developer convenience — not part of the core gameplay.

Both DB files are excluded by `.gitignore` by default.

Committing & pushing

A helper script `commit_and_push.ps1` was added to show the exact git commands to run locally (PowerShell). If PowerShell script execution is restricted, run the commands directly instead (see the script for the exact steps).

If you want `python main.py` to launch the game demo, I can wire that change for you.
