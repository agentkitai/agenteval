"""LangChain adapter for AgentEval."""

from __future__ import annotations

import time
from typing import Any

from agenteval.adapters import BaseAdapter
from agenteval.models import AgentResult


class LangChainAdapter(BaseAdapter):
    """Adapter for LangChain Runnable/Chain objects."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    def invoke(self, input: str) -> AgentResult:
        start = time.perf_counter()
        response = self.agent.invoke(input)
        latency_ms = int((time.perf_counter() - start) * 1000)

        # Extract output, tools, tokens based on response type
        output = ""
        tools_called: list[dict] = []
        tokens_in = 0
        tokens_out = 0

        if isinstance(response, dict):
            output = str(response.get("output", response))
        elif isinstance(response, str):
            output = response
        else:
            # AIMessage-like object
            output = str(getattr(response, "content", str(response)))
            tools_called = list(getattr(response, "tool_calls", []))
            usage = getattr(response, "usage_metadata", None)
            if usage and isinstance(usage, dict):
                tokens_in = usage.get("input_tokens", 0)
                tokens_out = usage.get("output_tokens", 0)

        return AgentResult(
            output=output,
            tools_called=tools_called,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
