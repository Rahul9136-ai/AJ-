"""
The Coordinator — the front door of the multi-agent system (AJ).

It reads the user's request, decides which specialist(s) to delegate to (it may
chain several), runs them via function calling, and synthesizes a single answer.
This is the orchestrator-worker pattern: one planner, many workers.
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional

import memory_store
from agents import SPECIALISTS
from agents.base import chat_loop
from agents.planning_agent import add_todo, render_todos

_SYSTEM_INTRO = """You are AJ, an AI assistant built by Purvi Technologies. You coordinate
a team of specialist agents to help a founder run their day and build their company.
When asked who you are, say you are AJ from Purvi Technologies.

Your team (call these via the matching ask_* tool):
{roster}
- save_todos    → persist tasks to the founder's running to-do list
- save_memory   → remember a durable fact about the founder or their company

How you work:
- Decide which specialist(s) the request needs. Delegate the actual work — don't do it
  yourself. You may call several specialists, including in sequence (e.g. research a
  market, then have the content agent write a post about it).
- Write each delegated `task` as a clear, self-contained instruction. Pass along any
  context the specialist needs (including findings from a previous specialist).
- If the founder shares a durable fact about themselves or the company (their name, what
  they're building, preferences, goals), call save_memory to remember it.
- When the planning agent suggests new to-dos, call save_todos to capture them.
- For simple chit-chat or clarifying questions, just answer directly.

Finish with a clear, synthesized response — integrate the specialists' outputs, don't
just paste them. Be concise and action-oriented.
"""


def _build_system() -> str:
    roster = "\n".join(
        f"- ask_{name:<16} → {spec.description.split('.')[0].lower()}"
        for name, spec in SPECIALISTS.items()
    )
    return _SYSTEM_INTRO.format(roster=roster)


def _build_tools() -> List[dict]:
    tools = [s.as_tool() for s in SPECIALISTS.values()]
    tools.append(
        {
            "type": "function",
            "function": {
                "name": "save_todos",
                "description": "Save one or more tasks to the founder's persistent to-do list.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Task descriptions to add to the to-do list.",
                        }
                    },
                    "required": ["tasks"],
                },
            },
        }
    )
    tools.append(
        {
            "type": "function",
            "function": {
                "name": "save_memory",
                "description": "Remember a durable fact about the founder or their company "
                "(name, what they're building, preferences, goals).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "facts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Short facts to remember long-term.",
                        }
                    },
                    "required": ["facts"],
                },
            },
        }
    )
    return tools


def _coerce_list(value) -> List[str]:
    """Normalize an arg that should be a list of strings (small models send odd shapes)."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            value = parsed if isinstance(parsed, list) else [value]
        except json.JSONDecodeError:
            value = [value]
    if not isinstance(value, list):
        value = [str(value)]
    return [str(v).strip() for v in value if str(v).strip() and len(str(v).strip()) > 1]


def _run_tool(name: str, tool_input: dict, on_event: Optional[Callable[[str], None]]) -> str:
    """Execute one coordinator tool call and return a string result."""
    if name == "save_todos":
        tasks = _coerce_list(tool_input.get("tasks", []))
        for t in tasks:
            add_todo(t)
        if on_event:
            on_event(f"[coordinator] saved {len(tasks)} to-do(s).")
        return f"Saved {len(tasks)} task(s). Current list:\n{render_todos()}"

    if name == "save_memory":
        facts = _coerce_list(tool_input.get("facts", []))
        saved = sum(1 for f in facts if memory_store.remember(f))
        if on_event:
            on_event(f"[coordinator] remembered {saved} fact(s).")
        return f"Remembered {saved} fact(s)."

    # Otherwise it's a delegation tool: ask_<specialist_name>.
    specialist_name = name[len("ask_"):]
    specialist = SPECIALISTS.get(specialist_name)
    if specialist is None:
        return f"Error: unknown specialist '{specialist_name}'."

    specialist.on_event = on_event
    return specialist.run(
        task=tool_input.get("task", ""),
        context=tool_input.get("context", ""),
    )


def coordinate(
    request: str,
    history: Optional[List[dict]] = None,
    on_event: Optional[Callable[[str], None]] = None,
    doc_context: str = "",
    attachments: Optional[List[dict]] = None,
    language: str = "en",
) -> str:
    """Run the full coordinator loop for one user request.

    `history`     — prior turns ([{role, content}, ...]) for conversational context.
    `doc_context` — extracted text from an uploaded document, injected as context.
    `attachments` — OpenAI-style image content parts (for multimodal requests).
    """
    tools = _build_tools()

    system = _build_system()
    if language and language != "en":
        system += f"\n\nIMPORTANT: The user has selected their language as '{language}'. Reply in that language unless they write to you in a different one."

    preamble_parts = [f"What you remember:\n{memory_store.render()}",
                      f"Current to-do list:\n{render_todos()}"]
    if doc_context:
        preamble_parts.append(f"Attached document:\n{doc_context}")
    preamble = "\n\n".join(preamble_parts)

    text = f"{preamble}\n\n---\n\nRequest: {request}"

    # Multimodal user turn when images are attached; plain text otherwise.
    if attachments:
        user_content = [{"type": "text", "text": text}] + attachments
    else:
        user_content = text

    messages: List[dict] = list(history or [])
    messages.append({"role": "user", "content": user_content})

    if on_event:
        on_event("[coordinator] thinking...")

    return chat_loop(
        system=system,
        messages=messages,
        tools=tools,
        tool_executor=lambda name, args: _run_tool(name, args, on_event),
        on_event=on_event,
    )
