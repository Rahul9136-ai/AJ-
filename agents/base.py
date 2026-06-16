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

import openai
from openai import OpenAI

import config

# One cached client per provider in the failover chain (built lazily).
_clients: dict = {}

# Errors that mean "this provider is temporarily unavailable — try the next one".
_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 529}


def _client_for(provider: dict) -> OpenAI:
    if provider["name"] not in _clients:
        _clients[provider["name"]] = OpenAI(
            base_url=provider["base_url"], api_key=provider["api_key"] or "x"
        )
    return _clients[provider["name"]]


def get_client() -> OpenAI:
    """Back-compat: the primary provider's client."""
    return _client_for(config.PROVIDER_CHAIN[0])


def complete(
    messages: List[dict],
    tools: Optional[List[dict]] = None,
    on_event: Optional[Callable[[str], None]] = None,
):
    """Make one chat completion, failing over across the provider chain on rate limits.

    Tries each provider in config.PROVIDER_CHAIN; on a 429 / quota / 5xx / connection
    error it moves to the next provider. Raises if all providers are exhausted, or
    immediately on a non-retryable error (e.g. a 400 bad request).
    """
    chain = config.PROVIDER_CHAIN
    last_err: Optional[Exception] = None
    for i, provider in enumerate(chain):
        try:
            return _client_for(provider).chat.completions.create(
                model=provider["model"],
                messages=messages,
                tools=tools or None,
                max_tokens=config.MAX_TOKENS,
            )
        except Exception as exc:  # noqa: BLE001 — classify below
            last_err = exc
            status = getattr(exc, "status_code", None)
            retryable = isinstance(
                exc, (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)
            ) or (status in _RETRYABLE_STATUS)
            if not retryable:
                raise
            if i + 1 < len(chain):
                if on_event:
                    on_event(f"[{provider['name']} unavailable -> switching to {chain[i + 1]['name']}]")
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError("No providers configured.")


def chat_loop(
    system: str,
    messages: List[dict],
    tools: Optional[List[dict]] = None,
    tool_executor: Optional[Callable[[str, dict], str]] = None,
    on_event: Optional[Callable[[str], None]] = None,
) -> str:
    """Run a function-calling loop until the model returns a plain answer.

    `tool_executor(name, args) -> str` is called for each tool the model invokes.
    Returns the model's final text content. Failover across providers is automatic.
    """
    convo: List[dict] = [{"role": "system", "content": system}] + list(messages)

    while True:
        response = complete(convo, tools=tools, on_event=on_event)
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
