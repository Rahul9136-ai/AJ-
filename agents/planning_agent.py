"""Planning & tasks specialist — daily plans, breakdowns, prioritization.

Keeps a simple persistent to-do list on disk so the plan survives between runs.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import List

from agents.base import Specialist
from config import WORKSPACE

TODO_PATH = os.path.join(WORKSPACE, "todos.json")


def _load_todos() -> List[dict]:
    if not os.path.exists(TODO_PATH):
        return []
    try:
        with open(TODO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_todos(todos: List[dict]) -> None:
    os.makedirs(WORKSPACE, exist_ok=True)
    with open(TODO_PATH, "w", encoding="utf-8") as f:
        json.dump(todos, f, indent=2)


def add_todo(text: str) -> None:
    todos = _load_todos()
    todos.append({"text": text, "done": False, "added": date.today().isoformat()})
    _save_todos(todos)


def get_todos() -> List[dict]:
    """Return the raw to-do list (for interactive rendering)."""
    return _load_todos()


def set_done(index: int, done: bool) -> None:
    todos = _load_todos()
    if 0 <= index < len(todos):
        todos[index]["done"] = done
        _save_todos(todos)


def delete_todo(index: int) -> None:
    todos = _load_todos()
    if 0 <= index < len(todos):
        todos.pop(index)
        _save_todos(todos)


def clear_done() -> None:
    _save_todos([t for t in _load_todos() if not t.get("done")])


def render_todos() -> str:
    todos = _load_todos()
    if not todos:
        return "(no open tasks)"
    lines = []
    for i, t in enumerate(todos, 1):
        mark = "x" if t.get("done") else " "
        lines.append(f"{i}. [{mark}] {t['text']}")
    return "\n".join(lines)


SYSTEM = """You are the Planning Agent for a founder building an AI company.

You turn vague intentions into an executable plan:
- Break big goals into concrete, ordered next actions (each doable in one sitting).
- Prioritize ruthlessly using impact vs. effort. Call out the ONE thing that matters most.
- Build a realistic daily plan: time-box tasks, protect deep-work blocks, leave slack.
- Flag dependencies and what's blocked on someone else.

When given the current to-do list as context, factor it in — don't ignore open items.

Output a clean, skimmable plan. Use a "Today's focus" line, then a time-blocked or
prioritized list. End with "Suggested new to-dos:" listing any tasks worth tracking,
one per line, so they can be saved.
"""

planning_agent = Specialist(
    name="planning_agent",
    description=(
        "Delegate planning work: daily/weekly plans, breaking a goal into next actions, "
        "prioritizing a backlog, or time-blocking a schedule. Pass the user's goals as the task."
    ),
    system=SYSTEM,
)
