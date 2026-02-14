"""Tests for capability coverage metrics."""

from __future__ import annotations

import pytest

from agenteval.capabilities import (
    CoverageConfig,
    check_coverage_threshold,
    compute_coverage,
    extract_capabilities,
    format_coverage_report,
    gap_analysis,
)
from agenteval.models import EvalCase, EvalResult, EvalRun, EvalSuite


def _case(name, caps=None, tags=None):
    grader_config = {}
    if caps:
        grader_config["capabilities"] = caps
    return EvalCase(
        name=name, input="test", expected={}, grader="exact",
        grader_config=grader_config, tags=tags or [],
    )


def _result(name, passed=True, score=1.0):
    return EvalResult(
        case_name=name, passed=passed, score=score, details={},
        agent_output="ok", tools_called=[], tokens_in=100,
        tokens_out=50, cost_usd=0.01, latency_ms=100,
    )


class TestExtractCapabilities:
    def test_from_grader_config(self):
        case = _case("test", caps=["tool_use", "reasoning"])
        assert extract_capabilities(case) == {"tool_use", "reasoning"}

    def test_from_tags(self):
        case = _case("test", tags=["cap:tool_use", "cap:reasoning", "other"])
        assert extract_capabilities(case) == {"tool_use", "reasoning"}

    def test_combined(self):
        case = _case("test", caps=["tool_use"], tags=["cap:reasoning"])
        assert extract_capabilities(case) == {"tool_use", "reasoning"}

    def test_string_capability(self):
        case = _case("test", caps="tool_use")
        assert extract_capabilities(case) == {"tool_use"}

    def test_no_capabilities(self):
        case = _case("test")
        assert extract_capabilities(case) == set()


class TestComputeCoverage:
    def test_full_coverage(self):
        cases = [
            _case("c1", caps=["tool_use"]),
            _case("c2", caps=["reasoning"]),
        ]
        suite = EvalSuite(name="test", agent="test:agent", cases=cases)

        results = [_result("c1"), _result("c2")]
        run = EvalRun(
            id="r1", suite="test", agent_ref="test:agent", config={},
            results=results, summary={"total": 2, "passed": 2, "failed": 0, "pass_rate": 1.0},
            created_at="2026-01-01T00:00:00Z",
        )

        config = CoverageConfig(declared_capabilities=["tool_use", "reasoning"])
        report = compute_coverage(run, suite, config)
        assert report.coverage_pct == 100.0
        assert report.untested_capabilities == 0
        assert len(report.capabilities) == 2

    def test_partial_coverage(self):
        cases = [_case("c1", caps=["tool_use"])]
        suite = EvalSuite(name="test", agent="test:agent", cases=cases)

        results = [_result("c1")]
        run = EvalRun(
            id="r1", suite="test", agent_ref="test:agent", config={},
            results=results, summary={"total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0},
            created_at="2026-01-01T00:00:00Z",
        )

        config = CoverageConfig(declared_capabilities=["tool_use", "reasoning", "error_recovery"])
        report = compute_coverage(run, suite, config)
        assert report.coverage_pct == pytest.approx(33.33, abs=1)
        assert report.untested_capabilities == 2
        assert "reasoning" in report.untested
        assert "error_recovery" in report.untested

    def test_no_declared_capabilities(self):
        cases = [_case("c1", caps=["tool_use"])]
        suite = EvalSuite(name="test", agent="test:agent", cases=cases)

        results = [_result("c1")]
        run = EvalRun(
            id="r1", suite="test", agent_ref="test:agent", config={},
            results=results, summary={"total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0},
            created_at="2026-01-01T00:00:00Z",
        )

        report = compute_coverage(run, suite)
        assert report.coverage_pct == 100.0

    def test_failed_tests(self):
        cases = [
            _case("c1", caps=["tool_use"]),
            _case("c2", caps=["tool_use"]),
        ]
        suite = EvalSuite(name="test", agent="test:agent", cases=cases)

        results = [_result("c1", passed=True), _result("c2", passed=False)]
        run = EvalRun(
            id="r1", suite="test", agent_ref="test:agent", config={},
            results=results, summary={"total": 2, "passed": 1, "failed": 1, "pass_rate": 0.5},
            created_at="2026-01-01T00:00:00Z",
        )

        report = compute_coverage(run, suite)
        assert len(report.capabilities) == 1
        cap = report.capabilities[0]
        assert cap.name == "tool_use"
        assert cap.test_count == 2
        assert cap.pass_rate == 0.5


class TestCheckCoverageThreshold:
    def test_above_threshold(self):
        from agenteval.capabilities import CoverageReport
        report = CoverageReport(
            total_capabilities=4, tested_capabilities=3,
            untested_capabilities=1, coverage_pct=75.0,
            capabilities=[], untested=["x"],
        )
        assert check_coverage_threshold(report, min_coverage_pct=70.0) is True

    def test_below_threshold(self):
        from agenteval.capabilities import CoverageReport
        report = CoverageReport(
            total_capabilities=4, tested_capabilities=2,
            untested_capabilities=2, coverage_pct=50.0,
            capabilities=[], untested=["x", "y"],
        )
        assert check_coverage_threshold(report, min_coverage_pct=70.0) is False

    def test_zero_threshold(self):
        from agenteval.capabilities import CoverageReport
        report = CoverageReport(
            total_capabilities=4, tested_capabilities=0,
            untested_capabilities=4, coverage_pct=0.0,
            capabilities=[], untested=[],
        )
        assert check_coverage_threshold(report, min_coverage_pct=0.0) is True


class TestFormatCoverageReport:
    def test_format(self):
        from agenteval.capabilities import CapabilityCoverage, CoverageReport
        report = CoverageReport(
            total_capabilities=2, tested_capabilities=1,
            untested_capabilities=1, coverage_pct=50.0,
            capabilities=[
                CapabilityCoverage(name="tool_use", test_count=3, passed_count=2,
                                   failed_count=1, pass_rate=0.67),
            ],
            untested=["reasoning"],
        )
        text = format_coverage_report(report)
        assert "50%" in text
        assert "tool_use" in text
        assert "reasoning" in text
        assert "Untested" in text


class TestGapAnalysis:
    def test_gap(self):
        cases = [_case("c1", caps=["tool_use"])]
        suite = EvalSuite(name="test", agent="test:agent", cases=cases)

        result = gap_analysis(suite, ["tool_use", "reasoning", "error_recovery"])
        assert "reasoning" in result["untested_capabilities"]
        assert "error_recovery" in result["untested_capabilities"]
        assert result["coverage_pct"] == pytest.approx(33.33, abs=1)

    def test_no_gap(self):
        cases = [_case("c1", caps=["tool_use"]), _case("c2", caps=["reasoning"])]
        suite = EvalSuite(name="test", agent="test:agent", cases=cases)

        result = gap_analysis(suite, ["tool_use", "reasoning"])
        assert result["untested_capabilities"] == []
        assert result["coverage_pct"] == 100.0

    def test_undeclared_tested(self):
        cases = [_case("c1", caps=["tool_use", "extra"])]
        suite = EvalSuite(name="test", agent="test:agent", cases=cases)

        result = gap_analysis(suite, ["tool_use"])
        assert "extra" in result["undeclared_tested"]
