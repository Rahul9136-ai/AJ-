"""Research & web specialist — free DuckDuckGo search (no API key) + synthesis.

Web search needs internet. If the `ddgs` package isn't installed or you're offline,
the agent answers from the local model's knowledge and says so.
"""

from __future__ import annotations

from agents.base import Specialist

SYSTEM = """You are the Research Agent. You answer questions and run market/competitive
research for a founder building an AI company.

Method:
- Use the web_search tool to get current, real information whenever the question is
  time-sensitive (prices, releases, who's funded, recent news). Call it more than once
  with different queries if needed.
- If web_search reports it is unavailable, answer from your own knowledge and clearly
  warn that the information may be outdated.
- Synthesize — don't dump links. Lead with the answer, then the supporting evidence.

Output format:
- A 2-4 sentence direct answer up top.
- Then "Key findings" as tight bullets.
- Then "Sources" with the URLs you actually used (omit if you didn't search).
- If evidence is thin or conflicting, say so plainly.
"""

# Local function tool — our code executes the search; the model just requests it.
WEB_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Returns titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."}
                },
                "required": ["query"],
            },
        },
    }
]


def _search(query: str, max_results: int = 5) -> str:
    """Run a free DuckDuckGo search. No API key required."""
    try:
        from ddgs import DDGS  # current package name
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # older package name
        except ImportError:
            return (
                "Web search is unavailable (run `pip install ddgs`). "
                "Answer from general knowledge and note the limitation."
            )

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:  # network errors, rate limits, etc.
        return (
            f"Web search failed ({exc}). "
            "Answer from general knowledge and note the limitation."
        )

    if not results:
        return "No results found."

    lines = []
    for r in results:
        title = r.get("title", "")
        href = r.get("href", "")
        body = r.get("body", "")
        lines.append(f"- {title}\n  {href}\n  {body}")
    return "\n".join(lines)


def _tool_executor(name: str, args: dict) -> str:
    if name == "web_search":
        return _search(args.get("query", ""))
    return f"Unknown tool: {name}"


research_agent = Specialist(
    name="research_agent",
    description=(
        "Delegate research that needs current information from the web: market sizing, "
        "competitor scans, pricing, technical comparisons, news, or fact-finding. "
        "This agent can search the web."
    ),
    system=SYSTEM,
    tools=WEB_TOOLS,
    tool_executor=_tool_executor,
)
