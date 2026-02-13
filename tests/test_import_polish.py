"""Tests for Batch 4: AgentLens Import Polish."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import httpx
import pytest

from agenteval.models import EvalCase, EvalSuite


# ── B4-S1: AgentLensClient ──────────────────────────────────────────────

class TestAgentLensClient:
    def test_init_defaults(self):
        from agenteval.importers.agentlens import AgentLensClient
        client = AgentLensClient("http://localhost:8000")
        assert client.server_url == "http://localhost:8000"
        assert client.api_key is None

    def test_init_with_api_key(self):
        from agenteval.importers.agentlens import AgentLensClient
        client = AgentLensClient("http://localhost:8000", api_key="secret")
        assert client.api_key == "secret"

    def test_fetch_session(self):
        from agenteval.importers.agentlens import AgentLensClient
        client = AgentLensClient("http://lens:8000", api_key="key1")
        session_data = {"id": "s1", "input": "hello", "output": "world", "events": []}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = session_data
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(get=MagicMock(return_value=mock_resp)))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            result = client.fetch_session("s1")

        assert result == session_data

    def test_list_sessions(self):
        from agenteval.importers.agentlens import AgentLensClient
        client = AgentLensClient("http://lens:8000")
        sessions = [{"id": "s1"}, {"id": "s2"}]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sessions
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.Client") as MockClient:
            mock_http = MagicMock()
            mock_http.get.return_value = mock_resp
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            result = client.list_sessions(filter_tags=["prod"], limit=10)

        assert result == sessions

    def test_fetch_session_error(self):
        from agenteval.importers.agentlens import AgentLensClient, AgentLensImportError
        client = AgentLensClient("http://lens:8000")

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )

        with patch("httpx.Client") as MockClient:
            mock_http = MagicMock()
            mock_http.get.return_value = mock_resp
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(AgentLensImportError, match="Failed to fetch"):
                client.fetch_session("bad-id")


# ── B4-S1: import_session function ──────────────────────────────────────

class TestImportSession:
    def test_import_session_from_data(self):
        from agenteval.importers.agentlens import import_session
        session_data = {
            "id": "sess-abc123",
            "agent": "mybot",
            "input": "What is 2+2?",
            "output": "4",
            "events": [
                {"type": "tool_call", "data": {"tool": "calculator", "args": {"expr": "2+2"}}},
            ],
        }
        case = import_session(session_data)
        assert isinstance(case, EvalCase)
        assert case.input == "What is 2+2?"
        assert "agentlens" in case.tags


# ── B4-S2: AssertionGenerator ───────────────────────────────────────────

class TestAssertionGenerator:
    def test_from_session_tool_calls(self):
        from agenteval.importers.assertions import AssertionGenerator
        session = {
            "input": "search for cats",
            "output": "Found cats",
            "events": [
                {"type": "tool_call", "data": {"tool": "web_search", "args": {"q": "cats"}}},
            ],
        }
        assertions = AssertionGenerator.from_session(session)
        tool_assertions = [a for a in assertions if a["type"] == "tool_check"]
        assert len(tool_assertions) == 1
        assert tool_assertions[0]["tool"] == "web_search"

    def test_from_session_contains(self):
        from agenteval.importers.assertions import AssertionGenerator
        session = {
            "input": "tell me about dogs",
            "output": "Dogs are loyal animals. They have been domesticated for thousands of years.",
            "events": [],
        }
        assertions = AssertionGenerator.from_session(session)
        contains_assertions = [a for a in assertions if a["type"] == "contains"]
        assert len(contains_assertions) >= 1

    def test_from_session_empty_output(self):
        from agenteval.importers.assertions import AssertionGenerator
        session = {"input": "hi", "output": "", "events": []}
        assertions = AssertionGenerator.from_session(session)
        assert assertions == []

    def test_from_session_multiple_tools(self):
        from agenteval.importers.assertions import AssertionGenerator
        session = {
            "input": "do stuff",
            "output": "Done",
            "events": [
                {"type": "tool_call", "data": {"tool": "read_file", "args": {"path": "/tmp"}}},
                {"type": "llm_call", "data": {}},
                {"type": "tool_call", "data": {"tool": "write_file", "args": {"path": "/out"}}},
            ],
        }
        assertions = AssertionGenerator.from_session(session)
        tool_assertions = [a for a in assertions if a["type"] == "tool_check"]
        assert len(tool_assertions) == 2

    def test_from_session_combined(self):
        from agenteval.importers.assertions import AssertionGenerator
        session = {
            "input": "search and summarize",
            "output": "Here is the summary of results.",
            "events": [
                {"type": "tool_call", "data": {"tool": "search"}},
            ],
        }
        assertions = AssertionGenerator.from_session(session)
        types = {a["type"] for a in assertions}
        assert "tool_check" in types
        assert "contains" in types

    def test_from_session_no_events_key(self):
        from agenteval.importers.assertions import AssertionGenerator
        session = {"input": "hi", "output": "hello"}
        assertions = AssertionGenerator.from_session(session)
        assert len(assertions) >= 1  # contains assertion from output


# ── B4-S3: InteractiveReviewer ──────────────────────────────────────────

class TestInteractiveReviewer:
    def _make_case(self, name="test", input_text="hi"):
        return EvalCase(name=name, input=input_text, expected={"output": "hello"}, grader="contains")

    def test_accept_all(self):
        from agenteval.importers.reviewer import InteractiveReviewer
        cases = [self._make_case("c1"), self._make_case("c2")]
        reviewer = InteractiveReviewer()
        with patch("builtins.input", return_value="y"):
            result = reviewer.review(cases)
        assert len(result) == 2

    def test_skip_all(self):
        from agenteval.importers.reviewer import InteractiveReviewer
        cases = [self._make_case("c1"), self._make_case("c2")]
        reviewer = InteractiveReviewer()
        with patch("builtins.input", return_value="n"):
            result = reviewer.review(cases)
        assert len(result) == 0

    def test_mixed_accept_skip(self):
        from agenteval.importers.reviewer import InteractiveReviewer
        cases = [self._make_case("c1"), self._make_case("c2"), self._make_case("c3")]
        reviewer = InteractiveReviewer()
        with patch("builtins.input", side_effect=["y", "n", "y"]):
            result = reviewer.review(cases)
        assert len(result) == 2
        assert result[0].name == "c1"
        assert result[1].name == "c3"

    def test_empty_cases(self):
        from agenteval.importers.reviewer import InteractiveReviewer
        reviewer = InteractiveReviewer()
        result = reviewer.review([])
        assert result == []


# ── B4-S4: Batch import ─────────────────────────────────────────────────

class TestBatchImport:
    def test_batch_import_basic(self):
        from agenteval.importers.agentlens import AgentLensClient, batch_import
        client = AgentLensClient("http://lens:8000")

        sessions_list = [{"id": "s1"}, {"id": "s2"}]
        session_details = {
            "s1": {"id": "s1", "agent": "bot", "input": "q1", "output": "a1", "events": []},
            "s2": {"id": "s2", "agent": "bot", "input": "q2", "output": "a2", "events": []},
        }

        with patch.object(client, "list_sessions", return_value=sessions_list), \
             patch.object(client, "fetch_session", side_effect=lambda sid: session_details[sid]):
            suite = batch_import(client)

        assert isinstance(suite, EvalSuite)
        assert len(suite.cases) == 2

    def test_batch_import_with_tags(self):
        from agenteval.importers.agentlens import AgentLensClient, batch_import
        client = AgentLensClient("http://lens:8000")

        with patch.object(client, "list_sessions", return_value=[]) as mock_list:
            suite = batch_import(client, filter_tags=["prod"], limit=10)

        mock_list.assert_called_once_with(filter_tags=["prod"], limit=10)
        assert len(suite.cases) == 0

    def test_batch_import_skips_invalid(self):
        from agenteval.importers.agentlens import AgentLensClient, batch_import
        client = AgentLensClient("http://lens:8000")

        sessions_list = [{"id": "s1"}, {"id": "s2"}]
        session_details = {
            "s1": {"id": "s1", "agent": "bot", "input": "", "output": "a1", "events": []},
            "s2": {"id": "s2", "agent": "bot", "input": "q2", "output": "a2", "events": []},
        }

        with patch.object(client, "list_sessions", return_value=sessions_list), \
             patch.object(client, "fetch_session", side_effect=lambda sid: session_details[sid]):
            suite = batch_import(client)

        assert len(suite.cases) == 1


# ── B4-S5: CLI commands ────────────────────────────────────────────────

class TestImportCLINew:
    def test_cli_single_session(self, tmp_path):
        from click.testing import CliRunner
        from agenteval.cli import cli

        out_path = str(tmp_path / "suite.yaml")
        session_data = {"id": "s1", "agent": "bot", "input": "hi", "output": "hello", "events": []}

        with patch("agenteval.importers.agentlens.AgentLensClient") as MockClient:
            instance = MockClient.return_value
            instance.fetch_session.return_value = session_data
            runner = CliRunner()
            result = runner.invoke(cli, [
                "import-agentlens", "--session", "s1",
                "--server", "http://lens:8000", "-o", out_path,
            ])

        assert result.exit_code == 0, result.output
        assert "Imported" in result.output

    def test_cli_batch(self, tmp_path):
        from click.testing import CliRunner
        from agenteval.cli import cli

        out_path = str(tmp_path / "suite.yaml")

        with patch("agenteval.importers.agentlens.AgentLensClient") as MockClient:
            instance = MockClient.return_value
            instance.list_sessions.return_value = [{"id": "s1"}]
            instance.fetch_session.return_value = {
                "id": "s1", "agent": "bot", "input": "hi", "output": "hello", "events": [],
            }
            runner = CliRunner()
            result = runner.invoke(cli, [
                "import-agentlens", "--batch",
                "--server", "http://lens:8000", "-o", out_path,
            ])

        assert result.exit_code == 0, result.output
        assert "Imported" in result.output
