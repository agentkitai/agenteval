"""Tests for AgentLens importer."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from agenteval.importers.agentlens import (
    AgentLensImportError,
    export_suite_yaml,
    import_agentlens,
)


def _create_agentlens_db(path: str, sessions=None, events=None):
    """Create a minimal AgentLens SQLite database for testing."""
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            agent TEXT,
            input TEXT,
            output TEXT,
            metadata TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            type TEXT NOT NULL,
            data TEXT,
            timestamp TEXT
        )
    """)
    if sessions:
        for s in sessions:
            conn.execute(
                "INSERT INTO sessions (id, agent, input, output, metadata, created_at) VALUES (?,?,?,?,?,?)",
                (s["id"], s.get("agent", "test-agent"), s.get("input", ""),
                 s.get("output", ""), s.get("metadata", "{}"), s.get("created_at", "2025-01-01T00:00:00")),
            )
    if events:
        for e in events:
            conn.execute(
                "INSERT INTO events (session_id, type, data, timestamp) VALUES (?,?,?,?)",
                (e["session_id"], e["type"], e.get("data", "{}"), e.get("timestamp", "2025-01-01T00:00:01")),
            )
    conn.commit()
    conn.close()


class TestImportAgentLens:
    def test_basic_import(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _create_agentlens_db(db_path, sessions=[
            {"id": "sess-001", "agent": "myagent", "input": "What is 2+2?", "output": "4"},
            {"id": "sess-002", "agent": "myagent", "input": "Hello", "output": "Hi there"},
        ])

        suite = import_agentlens(db_path)
        assert suite.name == "agentlens-import"
        assert len(suite.cases) == 2
        assert suite.cases[0].input in ("What is 2+2?", "Hello")
        assert all("agentlens" in c.tags for c in suite.cases)

    def test_import_with_events(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _create_agentlens_db(
            db_path,
            sessions=[{"id": "sess-001", "agent": "bot", "input": "Search for X", "output": "Found X"}],
            events=[
                {"session_id": "sess-001", "type": "llm_call", "data": json.dumps({"model": "gpt-4"})},
                {"session_id": "sess-001", "type": "tool_call", "data": json.dumps({"tool": "web_search"})},
                {"session_id": "sess-001", "type": "error", "data": json.dumps({"msg": "timeout"})},
            ],
        )

        suite = import_agentlens(db_path)
        assert len(suite.cases) == 1
        case = suite.cases[0]
        assert case.grader == "tool-check"  # tools detected → tool-check
        assert "web_search" in case.expected.get("tools", [])
        assert "has-errors" in case.tags

    def test_missing_db(self):
        with pytest.raises(AgentLensImportError, match="not found"):
            import_agentlens("/nonexistent/path.db")

    def test_wrong_schema(self, tmp_path):
        db_path = str(tmp_path / "bad.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE foo (id INTEGER)")
        conn.commit()
        conn.close()

        with pytest.raises(AgentLensImportError, match="missing required AgentLens tables"):
            import_agentlens(db_path)

    def test_empty_sessions(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        _create_agentlens_db(db_path)

        with pytest.raises(AgentLensImportError, match="No sessions found"):
            import_agentlens(db_path)

    def test_sessions_with_empty_inputs_skipped(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _create_agentlens_db(db_path, sessions=[
            {"id": "s1", "input": "", "output": "something"},
            {"id": "s2", "input": "  ", "output": "something"},
            {"id": "s3", "input": "valid input", "output": "valid output"},
        ])

        suite = import_agentlens(db_path)
        assert len(suite.cases) == 1
        assert suite.cases[0].input == "valid input"

    def test_all_empty_inputs_raises(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _create_agentlens_db(db_path, sessions=[
            {"id": "s1", "input": "", "output": "something"},
        ])

        with pytest.raises(AgentLensImportError, match="none produced valid"):
            import_agentlens(db_path)

    def test_limit(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _create_agentlens_db(db_path, sessions=[
            {"id": f"s{i}", "input": f"input {i}", "output": f"output {i}"}
            for i in range(10)
        ])

        suite = import_agentlens(db_path, limit=3)
        assert len(suite.cases) == 3

    def test_custom_suite_name(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _create_agentlens_db(db_path, sessions=[
            {"id": "s1", "input": "hi", "output": "hello"},
        ])

        suite = import_agentlens(db_path, suite_name="my-suite")
        assert suite.name == "my-suite"

    def test_invalid_grader(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _create_agentlens_db(db_path, sessions=[
            {"id": "s1", "input": "hi", "output": "hello"},
        ])
        with pytest.raises(AgentLensImportError, match="Invalid grader"):
            import_agentlens(db_path, grader="nonexistent")

    def test_session_ids_filter(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _create_agentlens_db(db_path, sessions=[
            {"id": "s1", "input": "a", "output": "b"},
            {"id": "s2", "input": "c", "output": "d"},
            {"id": "s3", "input": "e", "output": "f"},
        ])

        suite = import_agentlens(db_path, session_ids=["s1", "s3"])
        assert len(suite.cases) == 2


class TestExportSuiteYaml:
    def test_export_roundtrip(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _create_agentlens_db(db_path, sessions=[
            {"id": "s1", "agent": "bot", "input": "hi", "output": "hello"},
        ])

        suite = import_agentlens(db_path)
        out_path = str(tmp_path / "output" / "suite.yaml")
        result_path = export_suite_yaml(suite, out_path)

        assert Path(result_path).exists()
        with open(result_path) as f:
            data = yaml.safe_load(f)
        assert data["name"] == "agentlens-import"
        assert len(data["cases"]) == 1
        assert data["cases"][0]["input"] == "hi"

    def test_corrupt_db(self, tmp_path):
        db_path = str(tmp_path / "corrupt.db")
        with open(db_path, "w") as f:
            f.write("this is not a sqlite database")

        with pytest.raises(AgentLensImportError, match="Cannot open database|Database error"):
            import_agentlens(db_path)


class TestImportCLI:
    """Test the CLI import command via Click's test runner."""

    def test_import_command(self, tmp_path):
        from click.testing import CliRunner
        from agenteval.cli import cli

        db_path = str(tmp_path / "test.db")
        _create_agentlens_db(db_path, sessions=[
            {"id": "s1", "input": "hello", "output": "world"},
        ])
        out_path = str(tmp_path / "suite.yaml")

        runner = CliRunner()
        result = runner.invoke(cli, ["import", "--from", "agentlens", "--db", db_path, "-o", out_path])
        assert result.exit_code == 0
        assert "Imported 1 cases" in result.output

    def test_import_missing_db(self, tmp_path):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["import", "--from", "agentlens", "--db", "/nope.db", "-o", "out.yaml"])
        assert result.exit_code != 0
        assert "Import error" in result.output
