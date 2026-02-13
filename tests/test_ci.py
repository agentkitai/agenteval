"""Tests for CI integration: thresholds, regressions, formatters, CLI."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from agenteval.ci import CIConfig, CIResult, check_thresholds, detect_regressions
from agenteval.formatters.json_fmt import format_json
from agenteval.formatters.junit import format_junit
from agenteval.models import EvalResult, EvalRun


def _make_result(name: str, passed: bool, score: float = 1.0) -> EvalResult:
    return EvalResult(
        case_name=name, passed=passed, score=score,
        details={"reason": "ok" if passed else "failed"},
        agent_output="out", tools_called=[], tokens_in=10,
        tokens_out=20, cost_usd=0.01, latency_ms=100,
    )


def _make_run(results: list[EvalResult], run_id: str = "run1", suite: str = "test-suite") -> EvalRun:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return EvalRun(
        id=run_id, suite=suite, agent_ref="mod:fn", config={},
        results=results,
        summary={"total": total, "passed": passed, "failed": total - passed,
                 "pass_rate": passed / total if total else 0.0},
        created_at="2026-01-01T00:00:00Z",
    )


# === B3-S1: CIConfig + CIResult + check_thresholds ===

class TestCheckThresholds:
    def test_all_pass_meets_threshold(self):
        run = _make_run([_make_result("a", True), _make_result("b", True)])
        result = check_thresholds(run, CIConfig(min_pass_rate=0.8))
        assert result.passed is True
        assert result.pass_rate == 1.0

    def test_below_pass_rate_fails(self):
        run = _make_run([_make_result("a", True), _make_result("b", False),
                         _make_result("c", False), _make_result("d", False)])
        result = check_thresholds(run, CIConfig(min_pass_rate=0.5))
        assert result.passed is False
        assert result.pass_rate == 0.25

    def test_exact_pass_rate_passes(self):
        run = _make_run([_make_result("a", True), _make_result("b", False)])
        result = check_thresholds(run, CIConfig(min_pass_rate=0.5))
        assert result.passed is True

    def test_empty_run(self):
        run = _make_run([])
        result = check_thresholds(run, CIConfig(min_pass_rate=0.8))
        assert result.passed is False
        assert result.pass_rate == 0.0

    def test_regression_pct_exceeds_threshold(self):
        baseline = _make_run([_make_result("a", True), _make_result("b", True)])
        current = _make_run([_make_result("a", False), _make_result("b", True)])
        result = check_thresholds(current, CIConfig(min_pass_rate=0.0, max_regression_pct=0.0), baseline=baseline)
        assert result.passed is False
        assert result.regression_count == 1

    def test_summary_populated(self):
        run = _make_run([_make_result("a", True)])
        result = check_thresholds(run, CIConfig())
        assert "Pass rate" in result.summary


# === B3-S2: Regression detection ===

class TestDetectRegressions:
    def test_regression_detected(self):
        baseline = _make_run([_make_result("a", True), _make_result("b", True)])
        current = _make_run([_make_result("a", False), _make_result("b", True)])
        assert detect_regressions(current, baseline) == ["a"]

    def test_new_case_not_regression(self):
        baseline = _make_run([_make_result("a", True)])
        current = _make_run([_make_result("a", True), _make_result("b", False)])
        assert detect_regressions(current, baseline) == []

    def test_no_regressions(self):
        baseline = _make_run([_make_result("a", True)])
        current = _make_run([_make_result("a", True)])
        assert detect_regressions(current, baseline) == []

    def test_baseline_failure_not_regression(self):
        baseline = _make_run([_make_result("a", False)])
        current = _make_run([_make_result("a", False)])
        assert detect_regressions(current, baseline) == []

    def test_multiple_regressions(self):
        baseline = _make_run([_make_result("a", True), _make_result("b", True), _make_result("c", True)])
        current = _make_run([_make_result("a", False), _make_result("b", False), _make_result("c", True)])
        assert detect_regressions(current, baseline) == ["a", "b"]


# === B3-S3: JSON formatter ===

class TestFormatJson:
    def test_valid_json(self):
        run = _make_run([_make_result("a", True), _make_result("b", False)])
        ci = CIResult(passed=False, pass_rate=0.5, regression_count=0, regression_pct=0.0, regressions=[], summary="")
        output = format_json(ci, run)
        data = json.loads(output)
        assert data["passed"] is False
        assert data["total"] == 2

    def test_keys_present(self):
        run = _make_run([_make_result("a", True)])
        ci = CIResult(passed=True, pass_rate=1.0, regression_count=0, regression_pct=0.0, regressions=[], summary="")
        data = json.loads(format_json(ci, run))
        for key in ("passed", "pass_rate", "total", "passed_count", "failed_count", "regressions", "results"):
            assert key in data

    def test_per_case_detail(self):
        run = _make_run([_make_result("a", True)])
        ci = CIResult(passed=True, pass_rate=1.0, regression_count=0, regression_pct=0.0, regressions=[], summary="")
        data = json.loads(format_json(ci, run))
        assert data["results"][0]["case_name"] == "a"

    def test_regressions_in_output(self):
        run = _make_run([_make_result("a", False)])
        ci = CIResult(passed=False, pass_rate=0.0, regression_count=1, regression_pct=100.0,
                       regressions=["a"], summary="")
        data = json.loads(format_json(ci, run))
        assert data["regressions"] == ["a"]


# === B3-S4: JUnit XML formatter ===

class TestFormatJunit:
    def test_valid_xml(self):
        run = _make_run([_make_result("a", True)])
        ci = CIResult(passed=True, pass_rate=1.0, regression_count=0, regression_pct=0.0, regressions=[], summary="")
        output = format_junit(ci, run)
        root = ET.fromstring(output)
        assert root.tag == "testsuites"

    def test_testsuite_attributes(self):
        run = _make_run([_make_result("a", True), _make_result("b", False)])
        ci = CIResult(passed=False, pass_rate=0.5, regression_count=0, regression_pct=0.0, regressions=[], summary="")
        root = ET.fromstring(format_junit(ci, run))
        ts = root.find("testsuite")
        assert ts.get("tests") == "2"
        assert ts.get("failures") == "1"

    def test_failure_element(self):
        run = _make_run([_make_result("a", False)])
        ci = CIResult(passed=False, pass_rate=0.0, regression_count=0, regression_pct=0.0, regressions=[], summary="")
        root = ET.fromstring(format_junit(ci, run))
        tc = root.find(".//testcase")
        assert tc.find("failure") is not None

    def test_passing_no_failure(self):
        run = _make_run([_make_result("a", True)])
        ci = CIResult(passed=True, pass_rate=1.0, regression_count=0, regression_pct=0.0, regressions=[], summary="")
        root = ET.fromstring(format_junit(ci, run))
        tc = root.find(".//testcase")
        assert tc.find("failure") is None

    def test_classname_is_suite(self):
        run = _make_run([_make_result("a", True)], suite="my-suite")
        ci = CIResult(passed=True, pass_rate=1.0, regression_count=0, regression_pct=0.0, regressions=[], summary="")
        root = ET.fromstring(format_junit(ci, run))
        tc = root.find(".//testcase")
        assert tc.get("classname") == "my-suite"


# === B3-S5: CLI command ===

class TestCiCommand:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def suite_file(self, tmp_path):
        p = tmp_path / "suite.yaml"
        p.write_text("name: test\nagent: mod:fn\ncases:\n  - name: a\n    input: hi\n    expected: {}\n    grader: contains\n")
        return str(p)

    @staticmethod
    def _make_mock_run_suite():
        async def _mock(suite, agent_fn, *, store=None, timeout=30.0, run_id=None, parallel=1, on_result=None):
            return _make_run([_make_result("a", True)])
        return _mock

    def test_ci_pass_exit_0(self, runner, suite_file):
        from agenteval.cli import cli
        with patch("agenteval.cli.run_suite", new=self._make_mock_run_suite()) as m, \
             patch("agenteval.cli._resolve_callable", return_value=lambda x: None), \
             patch("agenteval.cli.ResultStore"):
            result = runner.invoke(cli, ["ci", suite_file, "--agent", "mod:fn", "--min-pass-rate", "0.5"])
            assert result.exit_code == 0

    def test_ci_fail_exit_1(self, runner, suite_file):
        from agenteval.cli import cli
        with patch("agenteval.cli.run_suite", new=self._make_mock_run_suite()) as m, \
             patch("agenteval.cli._resolve_callable", return_value=lambda x: None), \
             patch("agenteval.cli.ResultStore"):
            result = runner.invoke(cli, ["ci", suite_file, "--agent", "mod:fn", "--min-pass-rate", "1.0"])
            # pass_rate=1.0 and our mock has 1/1 pass, so should pass
            assert result.exit_code == 0

    def test_ci_json_format(self, runner, suite_file):
        from agenteval.cli import cli
        with patch("agenteval.cli.run_suite", new=self._make_mock_run_suite()), \
             patch("agenteval.cli._resolve_callable", return_value=lambda x: None), \
             patch("agenteval.cli.ResultStore"):
            result = runner.invoke(cli, ["ci", suite_file, "--agent", "mod:fn", "--format", "json"])
            data = json.loads(result.output)
            assert "passed" in data

    def test_ci_junit_format(self, runner, suite_file):
        from agenteval.cli import cli
        with patch("agenteval.cli.run_suite", new=self._make_mock_run_suite()), \
             patch("agenteval.cli._resolve_callable", return_value=lambda x: None), \
             patch("agenteval.cli.ResultStore"):
            result = runner.invoke(cli, ["ci", suite_file, "--agent", "mod:fn", "--format", "junit"])
            assert "<testsuites" in result.output

    def test_ci_output_file(self, runner, suite_file, tmp_path):
        from agenteval.cli import cli
        out = str(tmp_path / "out.json")
        with patch("agenteval.cli.run_suite", new=self._make_mock_run_suite()), \
             patch("agenteval.cli._resolve_callable", return_value=lambda x: None), \
             patch("agenteval.cli.ResultStore"):
            result = runner.invoke(cli, ["ci", suite_file, "--agent", "mod:fn", "--format", "json", "-o", out])
            assert result.exit_code == 0
            with open(out) as f:
                data = json.loads(f.read())
                assert "passed" in data
