#!/usr/bin/env python3
import argparse
import shlex
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys


DB_FILE = Path(__file__).parent / "tasks.db"

# single-letter aliases mapping (alias -> canonical)
ALIASES = {
    "a": "add",
    "l": "list",
    "m": "done",
    "r": "archive",
    "h": "help",
    "q": "exit",
    "e": "exit",
}

# tab-completion removed; REPL uses plain input()

# Command descriptions for REPL `help`
COMMAND_DESCRIPTIONS = {
    "add": "Add a new task: add <description>",
    "list": "List tasks (active by default). Use 'list --archived' to show archived tasks.",
    "done": "Mark a task completed: done <id>",
    "archive": "Archive (soft-delete) a task: archive <id>",
    "help": "Show this help message",
    "exit": "Exit the interactive prompt",
}


def get_conn(path: Path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT,
            completed_at TEXT
        )
        """
    )
    conn.commit()
    # ensure columns exist for older DBs
    cur = conn.execute("PRAGMA table_info(tasks)")
    cols = {row[1] for row in cur.fetchall()}
    if "archived" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    if "archived_at" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN archived_at TEXT")
    conn.commit()


# JSON migration removed — storage is SQLite-only.


def add_task(conn: sqlite3.Connection, description: str):
    created_at = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO tasks (description, completed, created_at) VALUES (?, 0, ?)",
        (description, created_at),
    )
    conn.commit()
    task_id = cur.lastrowid
    print(f"Added task {task_id}: {description}")


def list_tasks(conn: sqlite3.Connection, archived: bool = False):
    if archived:
        cur = conn.execute("SELECT id, description, completed, archived FROM tasks WHERE archived = 1 ORDER BY id")
    else:
        cur = conn.execute("SELECT id, description, completed, archived FROM tasks WHERE archived = 0 ORDER BY id")
    rows = cur.fetchall()
    if not rows:
        print("No tasks.")
        return
    for r in rows:
        status = "x" if r["completed"] else " "
        print(f"[{status}] {r['id']}: {r['description']}")


def complete_task(conn: sqlite3.Connection, task_id: int):
    cur = conn.execute("SELECT completed FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    if not row:
        print(f"Task {task_id} not found.")
        return
    if row["completed"]:
        print(f"Task {task_id} is already completed.")
        return
    completed_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE tasks SET completed = 1, completed_at = ? WHERE id = ?",
        (completed_at, task_id),
    )
    conn.commit()
    print(f"Marked {task_id} completed.")


def archive_task(conn: sqlite3.Connection, task_id: int):
    cur = conn.execute("SELECT archived FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    if not row:
        print(f"Task {task_id} not found.")
        return
    if row[0]:
        print(f"Task {task_id} is already archived.")
        return
    archived_at = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE tasks SET archived = 1, archived_at = ? WHERE id = ?", (archived_at, task_id))
    conn.commit()
    print(f"Archived {task_id}.")
# `clear` command removed — tasks persist in the database indefinitely.


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Simple task manager CLI (SQLite)")
    sub = parser.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add", aliases=["a"], help="Add a new task")
    p_add.add_argument("description", nargs="+", help="Task description")

    p_list = sub.add_parser("list", aliases=["l"], help="List tasks")
    p_list.add_argument("--archived", action="store_true", help="Show archived tasks")

    p_done = sub.add_parser("done", aliases=["m"], help="Mark task completed")
    p_done.add_argument("id", type=int)

    p_archive = sub.add_parser("archive", aliases=["r"], help="Archive a task")
    p_archive.add_argument("id", type=int)

    return parser.parse_args(argv)








def main(argv=None):
    args = parse_args(argv)
    conn = get_conn(DB_FILE)
    try:
        init_db(conn)
        if args.cmd:
            # canonicalize single-letter aliases
            cmd = args.cmd.lower()
            if cmd in ALIASES:
                cmd = ALIASES[cmd]

            # one-shot command mode
            if cmd == "add":
                add_task(conn, " ".join(args.description))
            elif cmd == "list":
                # respect --archived flag when present
                archived_flag = getattr(args, 'archived', False)
                list_tasks(conn, archived=archived_flag)
            elif cmd == "done":
                complete_task(conn, args.id)
            elif cmd == "archive":
                archive_task(conn, args.id)
            # `clear` removed: tasks are retained permanently in the DB
            else:
                print("Unknown command. Use --help for usage.")
        else:
            # interactive REPL mode
            repl(conn)
    finally:
        conn.close()


def repl(conn: sqlite3.Connection):
    """Simple interactive prompt. Commands: add, list, done, help, exit"""
    print("Task Manager — interactive mode. Type 'help' for commands.")
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = []
        try:
            parts = shlex.split(line)
        except Exception:
            parts = line.split()
        if not parts:
            continue
        cmd = parts[0].lower()
        # expand single-letter aliases
        if cmd in ALIASES:
            cmd = ALIASES[cmd]
        args = parts[1:]
        if cmd in ("exit", "quit"):
            break
        elif cmd == "help":
            # print detailed help with aliases
            # build alias list per command
            alias_map = {}
            for a, c in ALIASES.items():
                alias_map.setdefault(c, []).append(a)
            for name in sorted(COMMAND_DESCRIPTIONS.keys()):
                desc = COMMAND_DESCRIPTIONS[name]
                aliases = alias_map.get(name, [])
                short = [a for a in aliases if len(a) == 1]
                other = [a for a in aliases if len(a) > 1]
                parts = []
                if short:
                    parts.append(f"short: {', '.join(short)}")
                if other:
                    parts.append(f"aliases: {', '.join(other)}")
                alias_text = f" ({'; '.join(parts)})" if parts else ""
                print(f"{name}: {desc}{alias_text}")
            continue
        elif cmd == "add":
            if not args:
                print("Usage: add <description>")
                continue
            add_task(conn, " ".join(args))
            continue
        elif cmd == "list":
            list_tasks(conn)
            continue
        elif cmd == "archive":
            if not args:
                print("Usage: archive <id>")
                continue
            try:
                tid = int(args[0])
            except ValueError:
                print("Invalid id")
                continue
            archive_task(conn, tid)
            continue
        elif cmd == "done":
            if not args:
                print("Usage: done <id>")
                continue
            try:
                tid = int(args[0])
            except ValueError:
                print("Invalid id")
                continue
            complete_task(conn, tid)
            continue
        
        else:
            print(f"Unknown command: {cmd}. Type 'help'.")
            continue


if __name__ == "__main__":
    main()
