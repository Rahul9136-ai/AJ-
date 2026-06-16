"""Specialist agents for the multi-agent system."""

from agents.coding_agent import coding_agent
from agents.content_agent import content_agent
from agents.email_agent import email_agent
from agents.finance_agent import finance_agent
from agents.planning_agent import planning_agent
from agents.research_agent import research_agent
from agents.social_agent import social_agent
from agents.strategy_agent import strategy_agent

# The roster the coordinator can delegate to. Add a new Specialist here and it
# automatically becomes available as a tool — no orchestrator changes needed.
SPECIALISTS = {
    s.name: s
    for s in (
        email_agent,
        research_agent,
        planning_agent,
        content_agent,
        finance_agent,
        strategy_agent,
        social_agent,
        coding_agent,
    )
}

__all__ = ["SPECIALISTS"] + [f"{name}" for name in SPECIALISTS]
