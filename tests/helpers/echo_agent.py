"""Simple echo agent for CLI tests."""

from agenteval.models import AgentResult


def agent(input_text: str) -> AgentResult:
    """Echo the input back as output."""
    return AgentResult(output=input_text)
