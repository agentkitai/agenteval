"""CrewAI adapter for AgentEval."""

from __future__ import annotations

import time
from typing import Any

from agenteval.adapters import BaseAdapter
from agenteval.models import AgentResult


class CrewAIAdapter(BaseAdapter):
    """Adapter for CrewAI Crew objects."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    def invoke(self, input: str) -> AgentResult:
        start = time.perf_counter()
        response = self.agent.kickoff(inputs={"input": input})
        latency_ms = int((time.perf_counter() - start) * 1000)

        output = ""
        tools_called: list[dict] = []

        if isinstance(response, str):
            output = response
        else:
            output = str(getattr(response, "raw", str(response)))
            # Extract tool calls from tasks_output if available
            for task_out in getattr(response, "tasks_output", []):
                for tool in getattr(task_out, "tools_used", []):
                    tools_called.append({"name": str(tool)})

        return AgentResult(
            output=output,
            tools_called=tools_called,
            latency_ms=latency_ms,
        )
