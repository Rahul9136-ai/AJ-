# 🤖 AI Company Assistant — Multi-Agent System

A coordinator agent that routes your daily work to specialist AI agents, built to
help you run your day **and** build an AI company. Runs on **Google Gemini's free
tier** by default (fast, no cost) — and can switch to Groq or fully-local Ollama with
one env var.

## The team

| Agent | Handles |
|-------|---------|
| 📧 **Email Agent** | Draft replies, triage your inbox, summarize long threads |
| 🔎 **Research Agent** | Live web search, market & competitor scans, fact-finding |
| 🗓️ **Planning Agent** | Daily plans, breaking goals into next actions, prioritizing (persists your to-do list) |
| ✍️ **Content Agent** | Blog posts, LinkedIn/X copy, landing pages, outreach, docs |

A **Coordinator** reads each request, decides which specialist(s) to call (it can
chain them — e.g. *research a market → write a post about it*), then synthesizes one
answer. This is the orchestrator-worker pattern.

## How it works

```
You ──▶ Coordinator (local LLM + delegation tools)
              ├── ask_email_agent
              ├── ask_research_agent   (free DuckDuckGo web search)
              ├── ask_planning_agent   (reads/writes workspace/todos.json)
              ├── ask_content_agent
              └── save_todos
         ──▶ synthesized reply
```

Runs against a local Ollama model via its OpenAI-compatible API: the coordinator
delegates with function calling, and the research agent searches the web for free
with DuckDuckGo (no key; needs internet).

## Setup (one time)

1. **Get a free Gemini API key** → https://aistudio.google.com/apikey (sign in, "Create API key").
2. **Add it to a `.env` file** in this folder (copy `.env.example` to `.env`):
   ```
   GEMINI_API_KEY=your-key-here
   ```
   The app loads `.env` automatically — no `setx`, no restarting terminals.
3. **Install the Python deps** into the same Python you'll run with:
   ```bash
   python -m pip install -r requirements.txt
   ```

### Switching providers

Set `AGENT_PROVIDER` (in `.env` or the environment):

| Provider | Speed | Cost | Notes |
|----------|-------|------|-------|
| `gemini` (default) | Fast | Free tier | Needs `GEMINI_API_KEY` |
| `groq` | Very fast | Free tier | Needs `GROQ_API_KEY` (console.groq.com) |
| `ollama` | Slow on CPU | Free, offline | Needs Ollama installed + a pulled model |

> **Windows tip:** if you have multiple Python installs, always launch with
> `python -m ...` (e.g. `python -m streamlit run app.py`) so you use the interpreter
> that has the dependencies. A bare `streamlit run app.py` may pick a different Python
> and fail with `ModuleNotFoundError: No module named 'openai'`.

## Run it

**CLI — one-shot:**
```bash
python cli.py "draft a reply declining the partnership offer, then plan my afternoon"
```

**CLI — interactive chat (keeps context):**
```bash
python cli.py
```

**Streamlit dashboard:**
```bash
python -m streamlit run app.py
```

### 🎙️ Voice

- **Dashboard:** a mic recorder sits above the chat box — record your request and it's
  transcribed automatically. Tick **"🔊 Speak replies aloud"** in the sidebar to hear answers.
- **CLI voice mode:** `python cli.py --voice` — speak requests, hear replies. This needs a
  microphone library: `pip install pyaudio` (the dashboard mic does **not** need it).
- Speech-to-text uses the free Google recognizer (needs internet); text-to-speech is
  offline via your OS voice.

## Try these

- *"Research the top 5 AI note-taking competitors and write a LinkedIn post on our differentiator."*
- *"Summarize this email thread and draft a reply: [paste thread]"*
- *"Break my goal 'launch the MVP in 6 weeks' into a week-by-week plan."*
- *"What should I focus on today?"* (uses your saved to-do list)

## Extending it

Add a new specialist by creating one `Specialist` in `agents/` and registering it in
`agents/__init__.py`'s `SPECIALISTS` dict. It automatically becomes a delegation tool
for the coordinator — no orchestrator changes needed.

## Layout

```
config.py            Model, effort, workspace paths
agents/
  base.py            Specialist class + chat_loop (Ollama Chat Completions runner)
  email_agent.py     Each specialist = a system prompt (+ optional tools)
  research_agent.py  Free DuckDuckGo web search tool
  planning_agent.py  Persists todos.json
  content_agent.py
orchestrator.py      The Coordinator (manual tool-use loop)
cli.py               Terminal interface
app.py               Streamlit dashboard
```
