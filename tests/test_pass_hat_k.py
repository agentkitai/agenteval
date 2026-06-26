"""pass^k multi-trial reliability metric (#13)."""

import math

import pytest

from agenteval.flaky import (
    MultiRunResult,
    build_multi_run_report,
    pass_hat_k,
    reliability_at_k,
    reliability_summary,
)
from agenteval.models import EvalResult


def test_k1_is_pass_rate():
    assert pass_hat_k(3, 10, 1) == 0.3


def test_all_pass_is_one():
    assert pass_hat_k(5, 5, 3) == 1.0


def test_unbiased_estimator_without_replacement():
    # 4 passes of 5 trials, k=2: C(4,2)/C(5,2) = 6/10
    assert pass_hat_k(4, 5, 2) == pytest.approx(0.6)
    # k=3: C(4,3)/C(5,3) = 4/10
    assert pass_hat_k(4, 5, 3) == pytest.approx(0.4)


def test_fewer_than_k_passes_is_zero():
    assert pass_hat_k(1, 5, 2) == 0.0
    assert pass_hat_k(0, 5, 1) == 0.0


def test_insufficient_trials_is_nan():
    assert math.isnan(pass_hat_k(2, 2, 3))  # can't draw 3 from 2


def test_k_must_be_positive():
    with pytest.raises(ValueError):
        pass_hat_k(3, 5, 0)


def test_complement_of_pass_at_k_intuition():
    # All-pass ⇒ pass^k == 1 for any k≤n; a single failure drops pass^n to 0.
    assert pass_hat_k(5, 5, 5) == 1.0
    assert pass_hat_k(4, 5, 5) == 0.0  # not enough passes for all-5


def _mr(name, passed, runs):
    return MultiRunResult(
        case_name=name, runs=runs, passed_count=passed, pass_rate=passed / runs,
        mean_score=0.0, stddev_score=0.0, scores=[], consistency_score=0.0, is_flaky=0 < passed < runs,
    )


def test_reliability_at_k_and_summary():
    a = _mr("a", 4, 4)  # always passes
    b = _mr("b", 2, 4)  # flaky: pass^2 = C(2,2)/C(4,2) = 1/6
    assert reliability_at_k(a, 2) == 1.0
    assert reliability_at_k(b, 2) == pytest.approx(1 / 6)
    summary = reliability_summary([a, b], [2])
    assert summary["pass^2"] == pytest.approx((1.0 + 1 / 6) / 2)


def test_report_summary_includes_pass_hat_k():
    def res(passed):
        return EvalResult(
            case_name="c", passed=passed, score=1.0 if passed else 0.0, details={},
            agent_output="", tools_called=[], tokens_in=0, tokens_out=0, cost_usd=None, latency_ms=0,
        )

    report = build_multi_run_report({"c": [res(True), res(True), res(False)]}, num_runs=3)
    # 2 of 3 passed → pass^2 = C(2,2)/C(3,2) = 1/3; pass^3 = 0 (only 2 passes)
    assert report.summary["pass^2"] == pytest.approx(1 / 3)
    assert report.summary["pass^3"] == 0.0
