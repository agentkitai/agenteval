"""Tests for cost tracking and budget enforcement."""

from __future__ import annotations

import pytest

from agenteval.cost import (
    BudgetExceeded,
    check_budget,
    compute_cost,
    compute_cost_trend,
    compute_run_cost,
)
from agenteval.models import EvalResult, EvalRun


def _make_run(results=None):
    if results is None:
        results = [
            EvalResult(case_name="c1", passed=True, score=1.0, details={},
                       agent_output="ok", tools_called=[], tokens_in=1000,
                       tokens_out=500, cost_usd=0.01, latency_ms=100),
            EvalResult(case_name="c2", passed=True, score=0.8, details={},
                       agent_output="ok", tools_called=[], tokens_in=2000,
                       tokens_out=1000, cost_usd=0.02, latency_ms=200),
        ]
    return EvalRun(
        id="run1", suite="test", agent_ref="test:agent", config={},
        results=results,
        summary={"total": len(results), "passed": len(results), "failed": 0,
                 "pass_rate": 1.0, "total_cost_usd": 0.03},
        created_at="2026-01-01T00:00:00Z",
    )


class TestComputeCost:
    def test_default_pricing(self):
        cost = compute_cost(1000, 500)
        assert cost > 0

    def test_specific_model(self):
        cost = compute_cost(1000, 500, model="gpt-4o-mini")
        # input: 1.0 * 0.00015 + output: 0.5 * 0.0006
        expected = 1.0 * 0.00015 + 0.5 * 0.0006
        assert abs(cost - expected) < 1e-6

    def test_custom_price_table(self):
        table = {"my-model": {"input": 0.001, "output": 0.002}}
        cost = compute_cost(1000, 1000, model="my-model", price_table=table)
        assert abs(cost - 0.003) < 1e-6

    def test_zero_tokens(self):
        assert compute_cost(0, 0) == 0.0


class TestComputeRunCost:
    def test_uses_existing_cost(self):
        run = _make_run()
        report = compute_run_cost(run)
        assert abs(report.total_cost_usd - 0.03) < 1e-6
        assert len(report.per_case_costs) == 2

    def test_estimates_from_tokens(self):
        results = [
            EvalResult(case_name="c1", passed=True, score=1.0, details={},
                       agent_output="ok", tools_called=[], tokens_in=1000,
                       tokens_out=500, cost_usd=None, latency_ms=100),
        ]
        run = _make_run(results=results)
        report = compute_run_cost(run, model="gpt-4o-mini")
        assert report.total_cost_usd > 0


class TestCheckBudget:
    def test_within_budget(self):
        run = _make_run()
        report = check_budget(run, budget=1.0)
        assert report.budget_exceeded is False
        assert report.budget_remaining > 0

    def test_exceeds_budget(self):
        run = _make_run()
        report = check_budget(run, budget=0.001)
        assert report.budget_exceeded is True

    def test_per_test_budget(self):
        run = _make_run()
        report = check_budget(run, budget=1.0, per_test_budget=0.005)
        assert report.budget_exceeded is True  # c1=0.01 > 0.005


class TestCostTrend:
    def test_insufficient_data(self):
        result = compute_cost_trend([])
        assert result["trend"] == "insufficient_data"

    def test_stable(self):
        baselines = [
            {"total_cost_usd": 1.0},
            {"total_cost_usd": 1.01},
        ]
        result = compute_cost_trend(baselines)
        assert result["trend"] == "stable"

    def test_increasing(self):
        baselines = [
            {"total_cost_usd": 2.0},
            {"total_cost_usd": 1.0},
        ]
        result = compute_cost_trend(baselines)
        assert result["trend"] == "increasing_significantly"

    def test_decreasing(self):
        baselines = [
            {"total_cost_usd": 0.5},
            {"total_cost_usd": 1.0},
        ]
        result = compute_cost_trend(baselines)
        assert result["trend"] == "decreasing"


class TestBudgetExceeded:
    def test_exception_message(self):
        exc = BudgetExceeded(total_cost=5.0, budget=2.0)
        assert "5.0000" in str(exc)
        assert "2.0000" in str(exc)
