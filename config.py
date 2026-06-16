"""
Shared configuration for the multi-agent system.

Provider-agnostic: it talks to any OpenAI-compatible chat API. Pick a provider with
AGENT_PROVIDER (default: gemini). Each provider needs its own free API key in the env.

    gemini  -> free key at https://aistudio.google.com/apikey   (set GEMINI_API_KEY)
    groq    -> free key at https://console.groq.com/keys        (set GROQ_API_KEY)
    ollama  -> fully local, no key (must be installed + running)
"""

from __future__ import annotations

import os

# --- Minimal .env loader (no dependency) --------------------------------------- #
# Lets you keep keys in a `.env` file next to this module instead of using setx.
# Existing environment variables always win over the file.
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
            if _k and _v and _k not in os.environ:
                os.environ[_k] = _v

PROVIDER = os.environ.get("AGENT_PROVIDER", "gemini").lower()

# (base_url, default model, env var holding the API key)
_PRESETS = {
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.0-flash",
        "GEMINI_API_KEY",
    ),
    "groq": (
        "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile",
        "GROQ_API_KEY",
    ),
    "ollama": (
        "http://localhost:11434/v1",
        "llama3.2",
        "OLLAMA_API_KEY",  # unused; Ollama ignores the key
    ),
}

_base_url, _default_model, _key_env = _PRESETS.get(PROVIDER, _PRESETS["gemini"])

# Allow direct overrides for power users / other OpenAI-compatible providers.
BASE_URL = os.environ.get("OPENAI_BASE_URL", _base_url)
MODEL = os.environ.get("AGENT_MODEL", _default_model)
API_KEY = os.environ.get(_key_env) or os.environ.get("OPENAI_API_KEY") or "not-needed"

# Max tokens to generate per response.
MAX_TOKENS = int(os.environ.get("AGENT_MAX_TOKENS", "2048"))

# Optional dashboard password. If set (via AJ_PASSWORD in .env), the Streamlit app
# shows a lock screen. Leave empty to run without a login.
APP_PASSWORD = os.environ.get("AJ_PASSWORD", "").strip()

# Where the planning agent persists the running to-do list between sessions.
WORKSPACE = os.environ.get(
    "AGENT_WORKSPACE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace"),
)
