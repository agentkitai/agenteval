"""Tests for CrewAI and AutoGen adapters (FA-2, FA-3)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from agenteval.models import AgentResult


# ── FA-2: CrewAI Adapter ───────────────────────────────────────────────


class TestCrewAIAdapter:
    def test_invoke_basic(self):
        from agenteval.adapters.crewai import CrewAIAdapter

        mock_crew = MagicMock()
        result_obj = MagicMock()
        result_obj.raw = "crew output"
        result_obj.tasks_output = []
        mock_crew.kickoff.return_value = result_obj

        adapter = CrewAIAdapter(agent=mock_crew)
        result = adapter.invoke("hello")

        assert isinstance(result, AgentResult)
        assert result.output == "crew output"
        mock_crew.kickoff.assert_called_once_with(inputs={"input": "hello"})

    def test_invoke_string_result(self):
        from agenteval.adapters.crewai import CrewAIAdapter

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "plain string"

        adapter = CrewAIAdapter(agent=mock_crew)
        result = adapter.invoke("test")
        assert result.output == "plain string"

    def test_invoke_extracts_tool_calls(self):
        from agenteval.adapters.crewai import CrewAIAdapter

        mock_crew = MagicMock()
        task_output = MagicMock()
        task_output.raw = "used tools"
        task_output.tools_used = ["search", "calculator"]
        result_obj = MagicMock()
        result_obj.raw = "crew output with tools"
        result_obj.tasks_output = [task_output]
        mock_crew.kickoff.return_value = result_obj

        adapter = CrewAIAdapter(agent=mock_crew)
        result = adapter.invoke("use tools")
        assert result.output == "crew output with tools"
        assert len(result.tools_called) == 2

    def test_invoke_measures_latency(self):
        from agenteval.adapters.crewai import CrewAIAdapter

        mock_crew = MagicMock()

        def slow_kickoff(**kwargs):
            time.sleep(0.05)
            result_obj = MagicMock()
            result_obj.raw = "done"
            result_obj.tasks_output = []
            return result_obj

        mock_crew.kickoff.side_effect = slow_kickoff

        adapter = CrewAIAdapter(agent=mock_crew)
        result = adapter.invoke("test")
        assert result.latency_ms >= 40

    def test_import_error_when_not_installed(self):
        """CrewAI adapter should work without crewai installed (no import at module level)."""
        from agenteval.adapters.crewai import CrewAIAdapter

        # Just verify the class is importable and functional with mocks
        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "ok"
        adapter = CrewAIAdapter(agent=mock_crew)
        assert adapter.invoke("x").output == "ok"


class TestCrewAIRegistry:
    def test_get_adapter_crewai(self):
        from agenteval.adapters import get_adapter

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "hi"
        adapter = get_adapter("crewai", agent=mock_crew)
        assert adapter is not None


# ── FA-3: AutoGen Adapter ──────────────────────────────────────────────


class TestAutoGenAdapter:
    def test_invoke_basic(self):
        from agenteval.adapters.autogen import AutoGenAdapter

        mock_agent = MagicMock()
        chat_result = MagicMock()
        chat_result.chat_history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "response text"},
        ]
        mock_agent.initiate_chat.return_value = chat_result

        adapter = AutoGenAdapter(agent=mock_agent)
        result = adapter.invoke("hello")

        assert isinstance(result, AgentResult)
        assert result.output == "response text"

    def test_invoke_with_run_method(self):
        from agenteval.adapters.autogen import AutoGenAdapter

        mock_agent = MagicMock(spec=["run"])
        mock_agent.run.return_value = "plain output"

        adapter = AutoGenAdapter(agent=mock_agent)
        result = adapter.invoke("test")
        assert result.output == "plain output"

    def test_invoke_string_result(self):
        from agenteval.adapters.autogen import AutoGenAdapter

        mock_agent = MagicMock()
        mock_agent.initiate_chat.return_value = "string result"

        adapter = AutoGenAdapter(agent=mock_agent)
        result = adapter.invoke("test")
        assert result.output == "string result"

    def test_invoke_measures_latency(self):
        from agenteval.adapters.autogen import AutoGenAdapter

        mock_agent = MagicMock()

        def slow_chat(*args, **kwargs):
            time.sleep(0.05)
            return "done"

        mock_agent.initiate_chat.side_effect = slow_chat

        adapter = AutoGenAdapter(agent=mock_agent)
        result = adapter.invoke("test")
        assert result.latency_ms >= 40

    def test_import_error_when_not_installed(self):
        from agenteval.adapters.autogen import AutoGenAdapter

        mock_agent = MagicMock()
        mock_agent.initiate_chat.return_value = "ok"
        adapter = AutoGenAdapter(agent=mock_agent)
        assert adapter.invoke("x").output == "ok"


class TestAutoGenRegistry:
    def test_get_adapter_autogen(self):
        from agenteval.adapters import get_adapter

        mock_agent = MagicMock()
        mock_agent.initiate_chat.return_value = "hi"
        adapter = get_adapter("autogen", agent=mock_agent)
        assert adapter is not None
