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

_PRIMARY = os.environ.get("AGENT_PROVIDER", "gemini").lower()

# (base_url, default model, env var holding the API key — None for keyless/local)
_PRESETS = {
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.5-flash-lite",
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
        None,  # keyless / local
    ),
}


def _model_for(name: str, is_primary: bool) -> str:
    """Pick the model for a provider: <NAME>_MODEL env, else AGENT_MODEL (primary), else default."""
    m = os.environ.get(f"{name.upper()}_MODEL")
    if not m and is_primary:
        m = os.environ.get("AGENT_MODEL")
    return m or _PRESETS[name][1]


def _build_chain() -> list:
    """Ordered list of usable providers: primary first, then configured fallbacks.

    Failover order = AGENT_PROVIDER, then AGENT_FALLBACKS (default 'groq,gemini,ollama').
    A provider is skipped if it needs a key and none is set. Ollama (keyless/local) is
    always kept as the last-resort offline fallback.
    """
    fallbacks = os.environ.get("AGENT_FALLBACKS", "groq,gemini,ollama")
    order = [_PRIMARY] + [x.strip().lower() for x in fallbacks.split(",")]
    chain, seen = [], set()
    for name in order:
        if not name or name in seen or name not in _PRESETS:
            continue
        base_url, _, key_env = _PRESETS[name]
        api_key = os.environ.get(key_env) if key_env else "ollama"
        if key_env and not api_key:
            continue  # no key configured for this provider — skip it
        chain.append(
            {
                "name": name,
                "base_url": os.environ.get("OPENAI_BASE_URL", base_url) if name == _PRIMARY else base_url,
                "api_key": api_key,
                "model": _model_for(name, name == _PRIMARY),
            }
        )
        seen.add(name)
    if not chain:  # nothing configured — expose the primary so errors are clear
        base_url, _, key_env = _PRESETS.get(_PRIMARY, _PRESETS["gemini"])
        chain = [{"name": _PRIMARY, "base_url": base_url,
                  "api_key": (os.environ.get(key_env) if key_env else "ollama") or "not-needed",
                  "model": _model_for(_PRIMARY, True)}]
    return chain


# The failover chain, and back-compat single-provider attributes (primary = first).
PROVIDER_CHAIN = _build_chain()
CHAIN_NAMES = [p["name"] for p in PROVIDER_CHAIN]
PROVIDER = PROVIDER_CHAIN[0]["name"]
BASE_URL = PROVIDER_CHAIN[0]["base_url"]
MODEL = PROVIDER_CHAIN[0]["model"]
API_KEY = PROVIDER_CHAIN[0]["api_key"]

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
