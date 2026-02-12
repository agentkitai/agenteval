"""Tests for the statistical comparison engine."""

from __future__ import annotations


import pytest

from agenteval.compare import (
    ChangeStatus,
    compare_runs,
    compute_stats,
    confidence_interval,
    welch_t_test,
    _clean_scores,
    _welch_degrees_of_freedom,
    _welch_t_test_pure,
)
from agenteval.models import EvalResult, EvalRun


def _make_result(case_name: str, score: float, passed: bool = True) -> EvalResult:
    return EvalResult(
        case_name=case_name, passed=passed, score=score,
        details={}, agent_output="", tools_called=[],
        tokens_in=0, tokens_out=0, cost_usd=None, latency_ms=0,
    )


def _make_run(run_id: str, results: list[EvalResult], suite: str = "test") -> EvalRun:
    return EvalRun(
        id=run_id, suite=suite, agent_ref="test:agent",
        config={}, results=results,
        summary={"passed": sum(1 for r in results if r.passed),
                 "failed": sum(1 for r in results if not r.passed),
                 "total": len(results), "pass_rate": 0.0},
        created_at="2026-01-01T00:00:00",
    )


# --- compute_stats ---

class TestComputeStats:
    def test_basic(self):
        s = compute_stats("c1", [1.0, 2.0, 3.0])
        assert s.n == 3
        assert s.mean == pytest.approx(2.0)
        assert s.stddev == pytest.approx(1.0)

    def test_single_value(self):
        s = compute_stats("c1", [5.0])
        assert s.n == 1
        assert s.mean == pytest.approx(5.0)
        assert s.stddev == 0.0

    def test_empty(self):
        s = compute_stats("c1", [])
        assert s.n == 0
        assert s.mean == 0.0
        assert s.stddev == 0.0

    def test_identical_scores(self):
        s = compute_stats("c1", [3.0, 3.0, 3.0, 3.0])
        assert s.mean == pytest.approx(3.0)
        assert s.stddev == pytest.approx(0.0)

    def test_nan_filtered(self):
        s = compute_stats("c1", [1.0, float("nan"), 3.0])
        assert s.n == 2
        assert s.mean == pytest.approx(2.0)

    def test_inf_filtered(self):
        s = compute_stats("c1", [1.0, float("inf"), float("-inf"), 3.0])
        assert s.n == 2
        assert s.mean == pytest.approx(2.0)

    def test_all_nan(self):
        s = compute_stats("c1", [float("nan"), float("nan")])
        assert s.n == 0
        assert s.mean == 0.0


# --- clean_scores ---

class TestCleanScores:
    def test_normal(self):
        assert _clean_scores([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]

    def test_removes_nan_inf(self):
        assert _clean_scores([1.0, float("nan"), float("inf"), 2.0]) == [1.0, 2.0]


# --- welch_t_test ---

class TestWelchTTest:
    def test_identical_distributions(self):
        t, p = welch_t_test(5.0, 1.0, 10, 5.0, 1.0, 10)
        assert t == pytest.approx(0.0)
        assert p == pytest.approx(1.0)

    def test_very_different_means(self):
        t, p = welch_t_test(10.0, 1.0, 30, 0.0, 1.0, 30)
        assert p < 0.001

    def test_single_sample_returns_no_significance(self):
        t, p = welch_t_test(5.0, 0.0, 1, 3.0, 0.0, 1)
        assert t == 0.0
        assert p == 1.0

    def test_zero_variance_both_same_mean(self):
        """When both groups have zero variance and same mean → p=1."""
        t, p = welch_t_test(5.0, 0.0, 10, 5.0, 0.0, 10)
        assert p == 1.0

    def test_zero_variance_both_diff_mean(self):
        """When both groups have zero variance but different means → p=0 (deterministic)."""
        t, p = welch_t_test(5.0, 0.0, 10, 3.0, 0.0, 10)
        assert p == 0.0

    def test_pure_fallback_basic(self):
        t, p = _welch_t_test_pure(10.0, 1.0, 30, 0.0, 1.0, 30)
        assert p < 0.01

    def test_pure_zero_se(self):
        t, p = _welch_t_test_pure(5.0, 0.0, 10, 5.0, 0.0, 10)
        assert t == 0.0
        assert p == 1.0


# --- welch_degrees_of_freedom ---

class TestWelchDF:
    def test_equal_variance_equal_n(self):
        df = _welch_degrees_of_freedom(1.0, 10, 1.0, 10)
        assert df == pytest.approx(18.0)

    def test_zero_variance(self):
        df = _welch_degrees_of_freedom(0.0, 10, 0.0, 10)
        assert df == 0.0


# --- confidence_interval ---

class TestConfidenceInterval:
    def test_identical(self):
        lo, hi = confidence_interval(5.0, 1.0, 10, 5.0, 1.0, 10)
        assert lo < 0.0
        assert hi > 0.0
        # Should be symmetric around 0
        assert lo == pytest.approx(-hi, abs=0.01)

    def test_single_sample(self):
        lo, hi = confidence_interval(5.0, 0.0, 1, 3.0, 0.0, 1)
        assert lo == pytest.approx(2.0)
        assert hi == pytest.approx(2.0)


# --- compare_runs ---

class TestCompareRuns:
    def test_simple_two_runs_no_change(self):
        r1 = _make_run("r1", [_make_result("c1", 0.8)])
        r2 = _make_run("r2", [_make_result("c1", 0.8)])
        report = compare_runs([r1], [r2])
        assert len(report.cases) == 1
        assert report.cases[0].status == ChangeStatus.UNCHANGED

    def test_regression_detected(self):
        base = [_make_run(f"b{i}", [_make_result("c1", 0.9)]) for i in range(5)]
        target = [_make_run(f"t{i}", [_make_result("c1", 0.3)]) for i in range(5)]
        report = compare_runs(base, target)
        assert report.cases[0].status == ChangeStatus.REGRESSED
        assert len(report.regressions) == 1

    def test_improvement_detected(self):
        base = [_make_run(f"b{i}", [_make_result("c1", 0.3)]) for i in range(5)]
        target = [_make_run(f"t{i}", [_make_result("c1", 0.9)]) for i in range(5)]
        report = compare_runs(base, target)
        assert report.cases[0].status == ChangeStatus.IMPROVED
        assert len(report.improvements) == 1

    def test_new_case(self):
        r1 = _make_run("r1", [_make_result("c1", 0.8)])
        r2 = _make_run("r2", [_make_result("c1", 0.8), _make_result("c2", 0.5)])
        report = compare_runs([r1], [r2])
        statuses = {c.case_name: c.status for c in report.cases}
        assert statuses["c2"] == ChangeStatus.NEW

    def test_removed_case(self):
        r1 = _make_run("r1", [_make_result("c1", 0.8), _make_result("c2", 0.5)])
        r2 = _make_run("r2", [_make_result("c1", 0.8)])
        report = compare_runs([r1], [r2])
        statuses = {c.case_name: c.status for c in report.cases}
        assert statuses["c2"] == ChangeStatus.REMOVED

    def test_regression_threshold(self):
        """Small drop below threshold should NOT be regression."""
        base = [_make_run(f"b{i}", [_make_result("c1", 0.80)]) for i in range(5)]
        target = [_make_run(f"t{i}", [_make_result("c1", 0.78)]) for i in range(5)]
        report = compare_runs(base, target, regression_threshold=0.1)
        assert report.cases[0].status == ChangeStatus.UNCHANGED

    def test_multi_run_aggregation(self):
        """Multiple runs should aggregate scores per case."""
        base = [
            _make_run("b1", [_make_result("c1", 0.9)]),
            _make_run("b2", [_make_result("c1", 0.85)]),
            _make_run("b3", [_make_result("c1", 0.88)]),
        ]
        target = [
            _make_run("t1", [_make_result("c1", 0.5)]),
            _make_run("t2", [_make_result("c1", 0.45)]),
            _make_run("t3", [_make_result("c1", 0.48)]),
        ]
        report = compare_runs(base, target)
        assert report.cases[0].base.n == 3
        assert report.cases[0].target.n == 3
        assert report.cases[0].status == ChangeStatus.REGRESSED

    def test_empty_runs(self):
        """Empty run lists should produce empty report."""
        report = compare_runs([], [])
        assert len(report.cases) == 0
        assert report.summary == {"improved": 0, "regressed": 0, "unchanged": 0, "new": 0, "removed": 0}

    def test_alpha_parameter(self):
        report = compare_runs([], [], alpha=0.01)
        assert report.alpha == 0.01

    def test_report_properties(self):
        base = [_make_run(f"b{i}", [_make_result("c1", 0.9), _make_result("c2", 0.3)]) for i in range(5)]
        target = [_make_run(f"t{i}", [_make_result("c1", 0.3), _make_result("c2", 0.9)]) for i in range(5)]
        report = compare_runs(base, target)
        assert len(report.regressions) == 1
        assert len(report.improvements) == 1
        assert report.regressions[0].case_name == "c1"
        assert report.improvements[0].case_name == "c2"

    def test_one_group_zero_variance(self):
        """One group has zero variance, the other doesn't — should still work."""
        base = [_make_run(f"b{i}", [_make_result("c1", 0.9)]) for i in range(5)]
        target = [
            _make_run("t0", [_make_result("c1", 0.3)]),
            _make_run("t1", [_make_result("c1", 0.4)]),
            _make_run("t2", [_make_result("c1", 0.35)]),
            _make_run("t3", [_make_result("c1", 0.32)]),
            _make_run("t4", [_make_result("c1", 0.38)]),
        ]
        report = compare_runs(base, target)
        assert report.cases[0].status == ChangeStatus.REGRESSED

    def test_welch_df_n1(self):
        """Degrees of freedom with n=1 should not crash."""
        df = _welch_degrees_of_freedom(1.0, 1, 1.0, 10)
        assert df == 0.0

    def test_nan_scores_in_runs(self):
        """NaN scores should be filtered out."""
        r1 = _make_run("r1", [_make_result("c1", float("nan"))])
        r2 = _make_run("r2", [_make_result("c1", 0.5)])
        report = compare_runs([r1], [r2])
        # base has 0 valid scores, target has 1 — both < 2, so unchanged
        assert report.cases[0].status == ChangeStatus.UNCHANGED
