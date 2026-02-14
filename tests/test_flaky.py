"""Tests for flaky test detection."""

from __future__ import annotations

import pytest

from agenteval.flaky import (
    MultiRunResult,
    QuarantineConfig,
    aggregate_multi_run,
    build_multi_run_report,
    check_statistical_pass,
    should_quarantine,
)
from agenteval.models import EvalResult


def _result(name="case1", passed=True, score=1.0):
    return EvalResult(
        case_name=name, passed=passed, score=score, details={},
        agent_output="ok", tools_called=[], tokens_in=100,
        tokens_out=50, cost_usd=0.01, latency_ms=100,
    )


class TestAggregateMultiRun:
    def test_all_pass(self):
        results = [_result(score=1.0) for _ in range(5)]
        mr = aggregate_multi_run("case1", results)
        assert mr.runs == 5
        assert mr.passed_count == 5
        assert mr.pass_rate == 1.0
        assert mr.is_flaky is False
        assert mr.consistency_score == 1.0

    def test_all_fail(self):
        results = [_result(passed=False, score=0.0) for _ in range(5)]
        mr = aggregate_multi_run("case1", results)
        assert mr.pass_rate == 0.0
        assert mr.is_flaky is False

    def test_flaky(self):
        results = [_result(score=1.0), _result(passed=False, score=0.0),
                   _result(score=1.0), _result(passed=False, score=0.0),
                   _result(score=1.0)]
        mr = aggregate_multi_run("case1", results)
        assert mr.is_flaky is True
        assert mr.pass_rate == 0.6
        assert mr.consistency_score < 1.0

    def test_empty(self):
        mr = aggregate_multi_run("case1", [])
        assert mr.runs == 0
        assert mr.is_flaky is False

    def test_single_run(self):
        mr = aggregate_multi_run("case1", [_result()])
        assert mr.runs == 1
        assert mr.stddev_score == 0.0

    def test_mean_and_stddev(self):
        results = [_result(score=0.8), _result(score=1.0), _result(score=0.6)]
        mr = aggregate_multi_run("case1", results)
        assert abs(mr.mean_score - 0.8) < 1e-6
        assert mr.stddev_score > 0


class TestShouldQuarantine:
    def test_quarantine_flaky(self):
        mr = MultiRunResult(
            case_name="c1", runs=5, passed_count=3, pass_rate=0.6,
            mean_score=0.6, stddev_score=0.5, scores=[1, 0, 1, 0, 1],
            consistency_score=0.04, is_flaky=True,
        )
        assert should_quarantine(mr) is True

    def test_no_quarantine_stable_pass(self):
        mr = MultiRunResult(
            case_name="c1", runs=5, passed_count=5, pass_rate=1.0,
            mean_score=1.0, stddev_score=0.0, scores=[1, 1, 1, 1, 1],
            consistency_score=1.0, is_flaky=False,
        )
        assert should_quarantine(mr) is False

    def test_no_quarantine_mostly_failing(self):
        mr = MultiRunResult(
            case_name="c1", runs=5, passed_count=1, pass_rate=0.2,
            mean_score=0.2, stddev_score=0.4, scores=[0, 0, 0, 0, 1],
            consistency_score=0.36, is_flaky=True,
        )
        # fail_rate=0.8 > max_fail_rate=0.7 → not quarantined (just broken)
        assert should_quarantine(mr) is False

    def test_not_enough_runs(self):
        mr = MultiRunResult(
            case_name="c1", runs=2, passed_count=1, pass_rate=0.5,
            mean_score=0.5, stddev_score=0.5, scores=[1, 0],
            consistency_score=0.0, is_flaky=True,
        )
        assert should_quarantine(mr) is False

    def test_custom_config(self):
        config = QuarantineConfig(min_fail_rate=0.2, max_fail_rate=0.8, min_runs=2)
        mr = MultiRunResult(
            case_name="c1", runs=5, passed_count=1, pass_rate=0.2,
            mean_score=0.2, stddev_score=0.4, scores=[0, 0, 0, 0, 1],
            consistency_score=0.36, is_flaky=True,
        )
        assert should_quarantine(mr, config) is True


class TestStatisticalPass:
    def test_passes_at_threshold(self):
        mr = MultiRunResult(
            case_name="c1", runs=5, passed_count=4, pass_rate=0.8,
            mean_score=0.8, stddev_score=0.2, scores=[1, 1, 1, 1, 0],
            consistency_score=0.36, is_flaky=True,
        )
        assert check_statistical_pass(mr, required_pass_rate=0.8) is True

    def test_fails_below_threshold(self):
        mr = MultiRunResult(
            case_name="c1", runs=5, passed_count=3, pass_rate=0.6,
            mean_score=0.6, stddev_score=0.5, scores=[1, 0, 1, 0, 1],
            consistency_score=0.04, is_flaky=True,
        )
        assert check_statistical_pass(mr, required_pass_rate=0.8) is False


class TestBuildMultiRunReport:
    def test_report(self):
        all_results = {
            "case1": [_result() for _ in range(3)],
            "case2": [_result(name="case2"), _result(name="case2", passed=False, score=0.0),
                      _result(name="case2")],
        }
        report = build_multi_run_report(all_results, num_runs=3)
        assert report.total_runs_per_case == 3
        assert len(report.cases) == 2
        assert report.flaky_count == 1
        assert report.summary["stable_cases"] == 1
