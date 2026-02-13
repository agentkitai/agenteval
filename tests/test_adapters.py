"""Tests for adapter protocol, registry, LangChain adapter, and wiring."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from agenteval.models import AgentResult, EvalCase, EvalSuite


# ── FA-1: BaseAdapter protocol + registry ──────────────────────────────


class TestBaseAdapter:
    def test_cannot_instantiate_abc(self):
        from agenteval.adapters import BaseAdapter

        with pytest.raises(TypeError):
            BaseAdapter()

    def test_concrete_adapter_invoke(self):
        from agenteval.adapters import BaseAdapter

        class DummyAdapter(BaseAdapter):
            def invoke(self, input: str) -> AgentResult:
                return AgentResult(output=f"echo:{input}")

        adapter = DummyAdapter()
        result = adapter.invoke("hello")
        assert result.output == "echo:hello"
        assert isinstance(result, AgentResult)


class TestAdapterRegistry:
    def test_get_adapter_langchain(self):
        from agenteval.adapters import get_adapter

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"output": "hi"}
        adapter = get_adapter("langchain", agent=mock_agent)
        assert adapter is not None

    def test_get_adapter_unknown_raises(self):
        from agenteval.adapters import get_adapter

        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("nonexistent")

    def test_import_agent(self):
        from agenteval.adapters import _import_agent

        # Import something from stdlib
        obj = _import_agent("os.path:join")
        import os.path
        assert obj is os.path.join

    def test_import_agent_bad_format(self):
        from agenteval.adapters import _import_agent

        with pytest.raises(ValueError, match="module:attr"):
            _import_agent("no_colon_here")

    def test_import_agent_missing_module(self):
        from agenteval.adapters import _import_agent

        with pytest.raises(ImportError):
            _import_agent("nonexistent_module_xyz:thing")


# ── FA-4: LangChain adapter ────────────────────────────────────────────


class TestLangChainAdapter:
    def test_invoke_basic(self):
        from agenteval.adapters.langchain import LangChainAdapter

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"output": "response text"}

        adapter = LangChainAdapter(agent=mock_agent)
        result = adapter.invoke("hello")

        assert isinstance(result, AgentResult)
        assert result.output == "response text"
        assert result.latency_ms > 0 or result.latency_ms == 0  # just created
        mock_agent.invoke.assert_called_once_with("hello")

    def test_invoke_with_string_return(self):
        from agenteval.adapters.langchain import LangChainAdapter

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = "plain string"

        adapter = LangChainAdapter(agent=mock_agent)
        result = adapter.invoke("test")
        assert result.output == "plain string"

    def test_invoke_extracts_tool_calls(self):
        from agenteval.adapters.langchain import LangChainAdapter

        mock_agent = MagicMock()
        # Simulate AIMessage-like response with tool_calls
        response = MagicMock()
        response.__class__.__name__ = "AIMessage"
        response.content = "I used a tool"
        response.tool_calls = [{"name": "search", "args": {"q": "test"}}]
        # Make it not a dict or str so it goes to the else branch
        mock_agent.invoke.return_value = response

        adapter = LangChainAdapter(agent=mock_agent)
        result = adapter.invoke("use tools")
        assert result.output == "I used a tool"
        assert len(result.tools_called) == 1
        assert result.tools_called[0]["name"] == "search"

    def test_invoke_with_token_usage(self):
        from agenteval.adapters.langchain import LangChainAdapter

        mock_agent = MagicMock()
        response = MagicMock()
        response.content = "answer"
        response.tool_calls = []
        response.usage_metadata = {"input_tokens": 10, "output_tokens": 20}
        mock_agent.invoke.return_value = response

        adapter = LangChainAdapter(agent=mock_agent)
        result = adapter.invoke("q")
        assert result.tokens_in == 10
        assert result.tokens_out == 20

    def test_invoke_measures_latency(self):
        import time

        from agenteval.adapters.langchain import LangChainAdapter

        mock_agent = MagicMock()

        def slow_invoke(input_str):
            time.sleep(0.05)
            return {"output": "done"}

        mock_agent.invoke.side_effect = slow_invoke

        adapter = LangChainAdapter(agent=mock_agent)
        result = adapter.invoke("test")
        assert result.latency_ms >= 40  # at least ~50ms


# ── FA-5: Wiring into runner + CLI + loader ─────────────────────────────


class TestRunnerAdapter:
    def test_run_suite_with_adapter(self):
        from agenteval.adapters import BaseAdapter
        from agenteval.runner import run_suite

        class EchoAdapter(BaseAdapter):
            def invoke(self, input: str) -> AgentResult:
                return AgentResult(output=input)

        suite = EvalSuite(
            name="test",
            agent="dummy",
            cases=[
                EvalCase(
                    name="c1",
                    input="hello",
                    expected={"output": "hello"},
                    grader="exact",
                )
            ],
        )

        adapter = EchoAdapter()
        run = asyncio.run(run_suite(suite, lambda x: None, adapter=adapter))
        assert run.results[0].agent_output == "hello"
        assert run.results[0].passed is True


class TestLoaderAdapter:
    def test_load_suite_with_adapter_key(self, tmp_path):
        suite_yaml = tmp_path / "suite.yaml"
        suite_yaml.write_text(
            "name: test\n"
            "adapter: langchain\n"
            "agent: mymod:myfunc\n"
            "cases:\n"
            "  - name: c1\n"
            "    input: hi\n"
            "    expected:\n"
            "      output: hi\n"
        )
        suite = load_suite(str(suite_yaml))
        assert suite.defaults.get("adapter") == "langchain"


class TestCLIAdapterOptions:
    def test_run_command_has_adapter_option(self):
        """Verify the run command accepts --adapter."""
        from click.testing import CliRunner

        from agenteval.cli import cli

        runner = CliRunner()
        # Just check help mentions adapter
        result = runner.invoke(cli, ["run", "--help"])
        assert "--adapter" in result.output


from agenteval.loader import load_suite
