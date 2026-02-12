"""Tests for the CLI module."""

from __future__ import annotations

import textwrap

import pytest
from click.testing import CliRunner

from agenteval.cli import cli
from agenteval.models import EvalResult, EvalRun
from agenteval.store import ResultStore


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def suite_file(tmp_path):
    """Create a simple valid suite YAML file."""
    p = tmp_path / "suite.yaml"
    p.write_text(textwrap.dedent("""\
        name: test-suite
        agent: tests.helpers.echo_agent:agent
        cases:
          - name: case1
            input: hello
            expected:
              output: hello
            grader: exact
          - name: case2
            input: world
            expected:
              output: world
            grader: exact
    """))
    return str(p)


@pytest.fixture
def tagged_suite_file(tmp_path):
    p = tmp_path / "tagged.yaml"
    p.write_text(textwrap.dedent("""\
        name: tagged-suite
        agent: tests.helpers.echo_agent:agent
        cases:
          - name: fast-case
            input: hello
            expected:
              output: hello
            grader: exact
            tags: [fast]
          - name: slow-case
            input: world
            expected:
              output: world
            grader: exact
            tags: [slow]
    """))
    return str(p)


@pytest.fixture
def populated_db(tmp_path):
    """Create a DB with two runs for testing list/compare."""
    db_path = tmp_path / "test.db"
    store = ResultStore(db_path)
    for i, (pid, fid) in enumerate([("run_a", "suite-1"), ("run_b", "suite-1")]):
        results = [
            EvalResult(
                case_name="case1", passed=(i == 0), score=1.0 if i == 0 else 0.0,
                details={}, agent_output="out", tools_called=[],
                tokens_in=10, tokens_out=5, cost_usd=0.001, latency_ms=100,
            ),
            EvalResult(
                case_name="case2", passed=True, score=1.0,
                details={}, agent_output="out", tools_called=[],
                tokens_in=10, tokens_out=5, cost_usd=0.001, latency_ms=100,
            ),
        ]
        run = EvalRun(
            id=pid, suite=fid, agent_ref="test:agent", config={},
            results=results,
            summary={
                "total": 2, "passed": 2 if i == 1 else 1, "failed": 0 if i == 1 else 1,
                "pass_rate": 1.0 if i == 1 else 0.5,
                "total_cost_usd": 0.002, "total_tokens_in": 20,
                "total_tokens_out": 10, "avg_latency_ms": 100,
            },
            created_at=f"2026-01-0{i+1}T00:00:00Z",
        )
        store.save_run(run)
    store.close()
    return str(db_path)


# --- run command ---

class TestRunCommand:
    def test_missing_suite(self, runner):
        result = runner.invoke(cli, ["run", "--suite", "/nonexistent/suite.yaml"])
        assert result.exit_code != 0

    def test_suite_file_not_found_click(self, runner):
        """Click's exists=True should catch bad paths."""
        result = runner.invoke(cli, ["run", "--suite", "/no/such/file.yaml"])
        assert result.exit_code != 0

    def test_no_agent_specified(self, runner, tmp_path):
        p = tmp_path / "no_agent.yaml"
        p.write_text("name: x\ncases:\n  - name: c\n    input: hi\n    expected: {}\n    grader: exact\n")
        result = runner.invoke(cli, ["run", "--suite", str(p)])
        assert result.exit_code != 0
        assert "No agent specified" in result.output

    def test_bad_agent_format(self, runner, tmp_path):
        p = tmp_path / "s.yaml"
        p.write_text("name: x\nagent: nocolon\ncases:\n  - name: c\n    input: hi\n    expected: {}\n    grader: exact\n")
        result = runner.invoke(cli, ["run", "--suite", str(p)])
        assert result.exit_code != 0
        assert "module:attribute" in result.output

    def test_successful_run(self, runner, suite_file, tmp_path):
        db = str(tmp_path / "out.db")
        result = runner.invoke(cli, ["run", "--suite", suite_file, "--db", db, "-v"])
        assert result.exit_code == 0
        assert "Passed: 2" in result.output

    def test_tag_filter(self, runner, tagged_suite_file, tmp_path):
        db = str(tmp_path / "out.db")
        result = runner.invoke(cli, ["run", "--suite", tagged_suite_file, "--db", db, "--tag", "fast"])
        # Should only run 1 case
        assert "Total: 1" in result.output

    def test_tag_filter_no_match(self, runner, tagged_suite_file, tmp_path):
        db = str(tmp_path / "out.db")
        result = runner.invoke(cli, ["run", "--suite", tagged_suite_file, "--db", db, "--tag", "nonexistent"])
        assert result.exit_code != 0
        assert "No cases match" in result.output


# --- list command ---

class TestListCommand:
    def test_list_empty_db(self, runner, tmp_path):
        db = str(tmp_path / "empty.db")
        result = runner.invoke(cli, ["list", "--db", db])
        assert result.exit_code == 0
        assert "No runs found" in result.output

    def test_list_populated(self, runner, populated_db):
        result = runner.invoke(cli, ["list", "--db", populated_db])
        assert result.exit_code == 0
        assert "run_a" in result.output
        assert "run_b" in result.output

    def test_list_with_suite_filter(self, runner, populated_db):
        result = runner.invoke(cli, ["list", "--db", populated_db, "--suite-filter", "suite-1"])
        assert "run_a" in result.output

    def test_list_with_limit(self, runner, populated_db):
        result = runner.invoke(cli, ["list", "--db", populated_db, "--limit", "1"])
        lines = [line for line in result.output.strip().split("\n") if line.startswith("run_")]
        assert len(lines) == 1


# --- compare command ---

class TestCompareCommand:
    def test_compare_basic(self, runner, populated_db):
        result = runner.invoke(cli, ["compare", "run_a", "run_b", "--db", populated_db])
        assert result.exit_code == 0
        assert "Comparing" in result.output
        assert "case1" in result.output
        assert "case2" in result.output

    def test_compare_missing_run(self, runner, populated_db):
        result = runner.invoke(cli, ["compare", "run_a", "nonexistent", "--db", populated_db])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_compare_both_missing(self, runner, tmp_path):
        db = str(tmp_path / "empty.db")
        result = runner.invoke(cli, ["compare", "x", "y", "--db", db])
        assert result.exit_code != 0

    def test_compare_shows_changes(self, runner, populated_db):
        result = runner.invoke(cli, ["compare", "run_a", "run_b", "--db", populated_db])
        assert "improved" in result.output or "regressed" in result.output or "unchanged" in result.output


# --- version ---

class TestRunEdgeCases:
    def test_timeout_zero(self, runner, suite_file, tmp_path):
        db = str(tmp_path / "out.db")
        result = runner.invoke(cli, ["run", "--suite", suite_file, "--db", db, "--timeout", "0"])
        assert result.exit_code != 0
        assert "timeout must be positive" in result.output

    def test_timeout_negative(self, runner, suite_file, tmp_path):
        db = str(tmp_path / "out.db")
        result = runner.invoke(cli, ["run", "--suite", suite_file, "--db", db, "--timeout", "-1"])
        assert result.exit_code != 0

    def test_verbose_shows_failure_details(self, runner, tmp_path):
        """Verbose mode should show failure details for failing cases."""
        p = tmp_path / "fail.yaml"
        p.write_text(textwrap.dedent("""\
            name: fail-suite
            agent: tests.helpers.echo_agent:agent
            cases:
              - name: mismatch
                input: hello
                expected:
                  output: goodbye
                grader: exact
        """))
        db = str(tmp_path / "out.db")
        result = runner.invoke(cli, ["run", "--suite", str(p), "--db", db, "-v"])
        assert "FAIL" in result.output
        assert "mismatch" in result.output


class TestListEdgeCases:
    def test_limit_zero(self, runner, tmp_path):
        db = str(tmp_path / "empty.db")
        result = runner.invoke(cli, ["list", "--db", db, "--limit", "0"])
        assert result.exit_code != 0
        assert "limit must be positive" in result.output


class TestVersion:
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert "agenteval" in result.output
