"""Cost tracking and budget enforcement for AgentEval.

Tracks LLM API costs during eval runs and enforces budgets.
Supports per-test, per-suite budgets and cost trend reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agenteval.models import EvalResult, EvalRun

# Default pricing per 1K tokens (USD)
DEFAULT_PRICE_TABLE: Dict[str, Dict[str, float]] = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "claude-3.5-sonnet": {"input": 0.003, "output": 0.015},
    "default": {"input": 0.005, "output": 0.015},
}


@dataclass
class CostReport:
    """Cost report for an eval run."""
    total_cost_usd: float
    per_case_costs: List[Dict[str, Any]]
    budget: Optional[float] = None
    budget_exceeded: bool = False
    budget_remaining: Optional[float] = None


@dataclass
class BudgetExceeded(Exception):
    """Raised when a cost budget is exceeded."""
    total_cost: float
    budget: float
    message: str = ""

    def __post_init__(self) -> None:
        if not self.message:
            self.message = (
                f"Cost budget exceeded: ${self.total_cost:.4f} > ${self.budget:.4f}"
            )
        super().__init__(self.message)


def compute_cost(
    tokens_in: int,
    tokens_out: int,
    model: str = "default",
    price_table: Optional[Dict[str, Dict[str, float]]] = None,
) -> float:
    """Compute cost in USD for a given token usage.

    Args:
        tokens_in: Number of input tokens.
        tokens_out: Number of output tokens.
        model: Model name for pricing lookup.
        price_table: Custom price table. Falls back to DEFAULT_PRICE_TABLE.

    Returns:
        Cost in USD.
    """
    table = price_table or DEFAULT_PRICE_TABLE
    prices = table.get(model, table.get("default", {"input": 0.005, "output": 0.015}))
    cost = (tokens_in / 1000.0) * prices["input"] + (tokens_out / 1000.0) * prices["output"]
    return cost


def compute_run_cost(
    run: EvalRun,
    model: str = "default",
    price_table: Optional[Dict[str, Dict[str, float]]] = None,
) -> CostReport:
    """Compute total cost for an eval run.

    Uses cost_usd from results if available, otherwise estimates from tokens.
    """
    per_case = []
    total = 0.0

    for r in run.results:
        if r.cost_usd is not None and r.cost_usd > 0:
            cost = r.cost_usd
        else:
            cost = compute_cost(r.tokens_in, r.tokens_out, model, price_table)
        total += cost
        per_case.append({
            "case_name": r.case_name,
            "cost_usd": cost,
            "tokens_in": r.tokens_in,
            "tokens_out": r.tokens_out,
        })

    return CostReport(total_cost_usd=total, per_case_costs=per_case)


def check_budget(
    run: EvalRun,
    budget: float,
    per_test_budget: Optional[float] = None,
    model: str = "default",
    price_table: Optional[Dict[str, Dict[str, float]]] = None,
) -> CostReport:
    """Check if a run's cost is within budget.

    Args:
        run: The eval run to check.
        budget: Maximum total cost in USD.
        per_test_budget: Optional maximum cost per individual test.
        model: Model name for pricing.
        price_table: Custom price table.

    Returns:
        CostReport with budget status.

    Raises:
        BudgetExceeded: If the budget is exceeded.
    """
    report = compute_run_cost(run, model, price_table)
    report.budget = budget
    report.budget_remaining = budget - report.total_cost_usd
    report.budget_exceeded = report.total_cost_usd > budget

    # Check per-test budgets
    if per_test_budget is not None:
        for case_cost in report.per_case_costs:
            if case_cost["cost_usd"] > per_test_budget:
                report.budget_exceeded = True
                break

    return report


def compute_cost_trend(
    baselines: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute cost trends across baseline entries.

    Args:
        baselines: List of baseline entries with metrics containing total_cost_usd.

    Returns:
        Dict with trend information.
    """
    if len(baselines) < 2:
        return {"trend": "insufficient_data", "costs": []}

    costs = []
    for b in baselines:
        metrics = b if isinstance(b, dict) else b.metrics  # type: ignore[union-attr]
        cost = metrics.get("total_cost_usd", 0.0)
        costs.append(cost)

    # Most recent first
    if len(costs) >= 2:
        recent = costs[0]
        previous = costs[1]
        if previous > 0:
            change_pct = ((recent - previous) / previous) * 100
        else:
            change_pct = 0.0

        if change_pct > 20:
            trend = "increasing_significantly"
        elif change_pct > 5:
            trend = "increasing"
        elif change_pct < -5:
            trend = "decreasing"
        else:
            trend = "stable"
    else:
        trend = "stable"
        change_pct = 0.0

    return {
        "trend": trend,
        "change_pct": change_pct,
        "costs": costs,
        "latest": costs[0] if costs else 0.0,
    }
