"""Historical trend analysis and budget guardrails for AgentEval."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class TrendPoint:
    run_id: str
    created_at: float
    pass_rate: float
    avg_score: float
    avg_latency_ms: float
    total_cost: float


@dataclass
class TrendSummary:
    points: List[TrendPoint]
    direction: str  # "improving", "declining", "stable"
    avg_pass_rate: float
    pass_rate_delta: float  # last - first


@dataclass
class BudgetRule:
    metric: str  # pass_rate, avg_latency_ms, total_cost, avg_score
    max_value: Optional[float] = None
    min_value: Optional[float] = None


@dataclass
class BudgetViolation:
    rule: BudgetRule
    actual_value: float
    run_id: str


def _parse_timestamp(created_at: str) -> float:
    """Parse an ISO-format timestamp to epoch seconds."""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(created_at, fmt).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(created_at).timestamp()
    except Exception:
        return 0.0


def compute_trends(runs: list, limit: int = 20) -> TrendSummary:
    """Compute trend from list of EvalRun objects.

    Runs are sorted oldest-first before analysis.  Only the most recent
    *limit* runs are considered.
    """
    # Sort oldest first
    sorted_runs = sorted(runs, key=lambda r: r.created_at)[-limit:]

    points: List[TrendPoint] = []
    for run in sorted_runs:
        summary = run.summary or {}
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        pass_rate = summary.get("pass_rate", (passed / total if total else 0.0))
        avg_latency = summary.get("avg_latency_ms", 0.0)
        total_cost = summary.get("total_cost_usd", 0.0)

        # Compute avg_score from results if available, else from pass_rate
        if run.results:
            avg_score = sum(r.score for r in run.results) / len(run.results)
        else:
            avg_score = pass_rate

        points.append(TrendPoint(
            run_id=run.id,
            created_at=_parse_timestamp(run.created_at),
            pass_rate=pass_rate,
            avg_score=avg_score,
            avg_latency_ms=avg_latency,
            total_cost=total_cost,
        ))

    if not points:
        return TrendSummary(points=[], direction="stable", avg_pass_rate=0.0, pass_rate_delta=0.0)

    avg_pass_rate = sum(p.pass_rate for p in points) / len(points)
    pass_rate_delta = points[-1].pass_rate - points[0].pass_rate

    if pass_rate_delta > 0.05:
        direction = "improving"
    elif pass_rate_delta < -0.05:
        direction = "declining"
    else:
        direction = "stable"

    return TrendSummary(
        points=points,
        direction=direction,
        avg_pass_rate=avg_pass_rate,
        pass_rate_delta=pass_rate_delta,
    )


def load_budget_rules(path: str) -> List[BudgetRule]:
    """Load budget rules from a YAML file."""
    import yaml  # type: ignore[import-untyped]

    with open(path) as f:
        data = yaml.safe_load(f)

    rules: List[BudgetRule] = []
    for entry in data.get("rules", data if isinstance(data, list) else []):
        rules.append(BudgetRule(
            metric=entry["metric"],
            max_value=entry.get("max_value"),
            min_value=entry.get("min_value"),
        ))
    return rules


def check_budgets(rules: List[BudgetRule], runs: list) -> List[BudgetViolation]:
    """Check budget rules against recent runs. Returns violations."""
    if not runs:
        return []

    # Check the most recent run
    run = sorted(runs, key=lambda r: r.created_at)[-1]
    summary = run.summary or {}

    metric_map = {
        "pass_rate": summary.get("pass_rate", 0.0),
        "avg_latency_ms": summary.get("avg_latency_ms", 0.0),
        "total_cost": summary.get("total_cost_usd", 0.0),
        "avg_score": summary.get("pass_rate", 0.0),  # fallback
    }

    # Compute avg_score from results if available
    if run.results:
        metric_map["avg_score"] = sum(r.score for r in run.results) / len(run.results)

    violations: List[BudgetViolation] = []
    for rule in rules:
        actual = metric_map.get(rule.metric)
        if actual is None:
            continue
        if rule.max_value is not None and actual > rule.max_value:
            violations.append(BudgetViolation(rule=rule, actual_value=actual, run_id=run.id))
        if rule.min_value is not None and actual < rule.min_value:
            violations.append(BudgetViolation(rule=rule, actual_value=actual, run_id=run.id))

    return violations
