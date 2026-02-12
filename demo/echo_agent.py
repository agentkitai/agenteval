"""Demo agent that returns predictable responses for testing."""

from agenteval.models import AgentResult
import random


def agent(input_text: str) -> AgentResult:
    """Simple echo agent with some smarts for demo purposes."""
    responses = {
        "What is 2 + 2?": AgentResult(
            output="The answer is 4.",
            tokens_in=12, tokens_out=8, cost_usd=0.0003, latency_ms=150,
        ),
        "What is the capital of France?": AgentResult(
            output="The capital of France is Paris.",
            tokens_in=15, tokens_out=10, cost_usd=0.0004, latency_ms=200,
        ),
        "Summarize quantum computing in one sentence.": AgentResult(
            output="Quantum computing uses qubits that can exist in superposition to solve certain problems exponentially faster than classical computers.",
            tokens_in=18, tokens_out=25, cost_usd=0.0008, latency_ms=350,
        ),
        "Search for the weather in NYC": AgentResult(
            output="The weather in NYC is currently 72°F and sunny.",
            tools_called=[{"name": "web_search", "args": {"query": "weather NYC"}}],
            tokens_in=14, tokens_out=18, cost_usd=0.0005, latency_ms=280,
        ),
        "List 3 primary colors": AgentResult(
            output="1. Red\n2. Blue\n3. Yellow",
            tokens_in=10, tokens_out=12, cost_usd=0.0003, latency_ms=120,
        ),
    }

    for key, result in responses.items():
        if key.lower() in input_text.lower() or input_text.lower() in key.lower():
            return result

    return AgentResult(
        output=f"I received: {input_text}",
        tokens_in=10, tokens_out=15, cost_usd=0.0002, latency_ms=100,
    )


def flaky_agent(input_text: str) -> AgentResult:
    """Agent that occasionally fails — useful for regression demo."""
    import copy
    result = agent(input_text)
    result = AgentResult(
        output=result.output,
        tools_called=list(result.tools_called),
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )
    # Randomly degrade some outputs so graders fail
    if random.random() < 0.4:
        result.output = "I'm not sure about that."
        result.tools_called = []
    return result
