# Task Manager CLI

A minimal command-line task manager. Tasks are stored in `tasks.db` (SQLite) in the same folder.

Usage examples:

- Add a task:
 - Add a task:

```powershell
python taskmanager.py add "Buy milk"
```
Short alias: `python main.py a "Buy milk"`

- List active tasks:
 - List active tasks:

```powershell
python taskmanager.py list
```
Short alias: `python taskmanager.py l`

- List archived tasks:
 - List archived tasks:

```powershell
python taskmanager.py list --archived
```

- Mark a task completed (by id):
 - Mark a task completed (by id):

```powershell
python taskmanager.py done 1
```
Short alias: `python taskmanager.py m 1`

- Archive a task (soft-archive):
 - Archive a task (soft-archive):

```powershell
python taskmanager.py archive 1
```
Short alias: `python taskmanager.py r 1`

Notes:
- No external dependencies required; runs with Python 3.7+
- Tasks are stored in `tasks.db` (SQLite) with columns `id`, `description`, `completed`, timestamps, and `archived` state.
- This project no longer supports JSON storage; only SQLite (`tasks.db`) is used.

One-letter aliases (also available in interactive mode):

- `a` = add
- `l` = list
- `m` = mark done (done)
- `r` = archive
- `h` = help
- `q` = quit / exit

Tab completion support has been removed; the REPL uses the simple built-in prompt without tab completion.
