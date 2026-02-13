"""AutoGen adapter for AgentEval."""

from __future__ import annotations

import time
from typing import Any

from agenteval.adapters import BaseAdapter
from agenteval.models import AgentResult


class AutoGenAdapter(BaseAdapter):
    """Adapter for AutoGen agent objects."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    def invoke(self, input: str) -> AgentResult:
        start = time.perf_counter()

        # Prefer .run() if available, else .initiate_chat()
        if hasattr(self.agent, "run") and not hasattr(self.agent, "initiate_chat"):
            response = self.agent.run(input)
        else:
            response = self.agent.initiate_chat(message=input)

        latency_ms = int((time.perf_counter() - start) * 1000)

        output = ""
        if isinstance(response, str):
            output = response
        else:
            # Extract last message from chat_history
            chat_history = getattr(response, "chat_history", None)
            if chat_history and isinstance(chat_history, list):
                last_msg = chat_history[-1]
                if isinstance(last_msg, dict):
                    output = str(last_msg.get("content", str(last_msg)))
                else:
                    output = str(last_msg)
            else:
                output = str(response)

        return AgentResult(
            output=output,
            latency_ms=latency_ms,
        )
