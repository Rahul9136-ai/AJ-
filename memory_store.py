"""
Long-term memory for AJ.

Stores durable facts about the user and their company in a JSON file so AJ
remembers them across sessions. Kept deliberately simple: a flat list of short
fact strings, injected into the coordinator's context on every request.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import List

from config import WORKSPACE

MEMORY_PATH = os.path.join(WORKSPACE, "memory.json")


def _load() -> List[dict]:
    if not os.path.exists(MEMORY_PATH):
        return []
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: List[dict]) -> None:
    os.makedirs(WORKSPACE, exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def remember(fact: str) -> bool:
    """Store a fact. Returns False if it's blank or a near-duplicate."""
    fact = (fact or "").strip()
    if len(fact) < 3:
        return False
    items = _load()
    existing = {i["fact"].lower() for i in items}
    if fact.lower() in existing:
        return False
    items.append({"fact": fact, "added": date.today().isoformat()})
    _save(items)
    return True


def recall() -> List[str]:
    return [i["fact"] for i in _load()]


def render() -> str:
    facts = recall()
    if not facts:
        return "(nothing remembered yet)"
    return "\n".join(f"- {f}" for f in facts)


def forget(index: int) -> bool:
    """Delete the fact at the given 0-based index."""
    items = _load()
    if 0 <= index < len(items):
        items.pop(index)
        _save(items)
        return True
    return False


def clear() -> None:
    _save([])
