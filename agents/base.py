"""
Base specialist agent + the shared tool-calling loop.

Everything runs against a local Ollama server via its OpenAI-compatible Chat
Completions API. A `Specialist` is one persona (a system prompt) plus optional
local tools; `chat_loop` drives the function-calling loop used by both the
specialists and the coordinator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from openai import OpenAI

from config import API_KEY, BASE_URL, MAX_TOKENS, MODEL

# Lazily-built client pointed at the configured OpenAI-compatible provider. Deferred
# so imports work (CLI help, tests, Streamlit page load) even before the key is set.
_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    return _client


def chat_loop(
    system: str,
    messages: List[dict],
    tools: Optional[List[dict]] = None,
    tool_executor: Optional[Callable[[str, dict], str]] = None,
    on_event: Optional[Callable[[str], None]] = None,
    model: str = MODEL,
) -> str:
    """Run a function-calling loop until the model returns a plain answer.

    `tool_executor(name, args) -> str` is called for each tool the model invokes.
    Returns the model's final text content.
    """
    convo: List[dict] = [{"role": "system", "content": system}] + list(messages)

    while True:
        response = get_client().chat.completions.create(
            model=model,
            messages=convo,
            tools=tools or None,
            max_tokens=MAX_TOKENS,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return (msg.content or "").strip()

        # Preserve the assistant's tool-call message, then answer each call.
        convo.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if on_event:
                on_event(f"-> {name}")
            result = tool_executor(name, args) if tool_executor else f"No executor for {name}."
            convo.append({"role": "tool", "tool_call_id": call.id, "content": result})


@dataclass
class Specialist:
    """A single-purpose agent backed by one local persona."""

    name: str
    description: str
    system: str
    # Chat-Completions function-tool definitions this specialist may use locally.
    tools: List[dict] = field(default_factory=list)
    # Executes this specialist's own tools: (name, args) -> result string.
    tool_executor: Optional[Callable[[str, dict], str]] = None
    model: str = MODEL
    on_event: Optional[Callable[[str], None]] = None

    def _emit(self, text: str) -> None:
        if self.on_event:
            self.on_event(text)

    def run(self, task: str, context: str = "") -> str:
        """Execute the task and return the specialist's final text response."""
        self._emit(f"[{self.name}] working...")

        user_content = task if not context else f"{context}\n\n---\n\nTask: {task}"
        out = chat_loop(
            system=self.system,
            messages=[{"role": "user", "content": user_content}],
            tools=self.tools or None,
            tool_executor=self.tool_executor,
            on_event=self.on_event,
            model=self.model,
        )

        self._emit(f"[{self.name}] done.")
        return out

    def as_tool(self) -> dict:
        """The function-tool definition the coordinator uses to delegate here."""
        return {
            "type": "function",
            "function": {
                "name": f"ask_{self.name}",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "A clear, self-contained instruction for this specialist.",
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional background (prior findings, user details).",
                        },
                    },
                    "required": ["task"],
                },
            },
        }
