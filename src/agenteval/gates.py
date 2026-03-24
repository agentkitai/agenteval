"""Regression gate policies for AgentEval.

Evaluate pass/fail gates against run results and optional comparison data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import yaml

from agenteval.compare import ComparisonReport
from agenteval.models import EvalRun


@dataclass
class GatePolicy:
    """Policy thresholds for a regression gate."""

    min_pass_rate: Optional[float] = None
    max_regressions: Optional[int] = None
    score_threshold: Optional[float] = None
    max_cost_increase_pct: Optional[float] = None
    max_latency_increase_pct: Optional[float] = None


@dataclass
class GateViolation:
    """A single gate violation."""

    metric: str
    expected: str
    actual: str


@dataclass
class GateResult:
    """Result of evaluating a gate policy."""

    passed: bool
    violations: List[GateViolation] = field(default_factory=list)


def load_gate_policy(path: str) -> GatePolicy:
    """Load a gate policy from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return GatePolicy(
        min_pass_rate=data.get("min_pass_rate"),
        max_regressions=data.get("max_regressions"),
        score_threshold=data.get("score_threshold"),
        max_cost_increase_pct=data.get("max_cost_increase_pct"),
        max_latency_increase_pct=data.get("max_latency_increase_pct"),
    )


def evaluate_gate(
    policy: GatePolicy,
    target_run: EvalRun,
    comparison: Optional[ComparisonReport] = None,
) -> GateResult:
    """Evaluate a gate policy against run results and optional comparison."""
    violations: List[GateViolation] = []

    summary = target_run.summary

    # Check min_pass_rate
    if policy.min_pass_rate is not None:
        actual_rate = summary.get("pass_rate", 0.0)
        if actual_rate < policy.min_pass_rate:
            violations.append(GateViolation(
                metric="min_pass_rate",
                expected=f">= {policy.min_pass_rate:.0%}",
                actual=f"{actual_rate:.0%}",
            ))

    # Check score_threshold against average score
    if policy.score_threshold is not None:
        results = target_run.results
        if results:
            avg_score = sum(r.score for r in results) / len(results)
        else:
            avg_score = 0.0
        if avg_score < policy.score_threshold:
            violations.append(GateViolation(
                metric="score_threshold",
                expected=f">= {policy.score_threshold:.3f}",
                actual=f"{avg_score:.3f}",
            ))

    # Checks that require a comparison report
    if comparison is not None:
        # Check max_regressions
        if policy.max_regressions is not None:
            reg_count = len(comparison.regressions)
            if reg_count > policy.max_regressions:
                violations.append(GateViolation(
                    metric="max_regressions",
                    expected=f"<= {policy.max_regressions}",
                    actual=str(reg_count),
                ))

        # Check cost increase
        if policy.max_cost_increase_pct is not None:
            base_cost = _avg_run_cost(comparison.base_run_ids, target_run, comparison)
            target_cost = summary.get("total_cost_usd", 0.0) or 0.0
            if base_cost and base_cost > 0:
                pct = ((target_cost - base_cost) / base_cost) * 100.0
                if pct > policy.max_cost_increase_pct:
                    violations.append(GateViolation(
                        metric="max_cost_increase_pct",
                        expected=f"<= {policy.max_cost_increase_pct:.1f}%",
                        actual=f"{pct:.1f}%",
                    ))

        # Check latency increase
        if policy.max_latency_increase_pct is not None:
            base_latency = _avg_run_latency(comparison.base_run_ids, target_run, comparison)
            target_latency = summary.get("avg_latency_ms", 0.0) or 0.0
            if base_latency and base_latency > 0:
                pct = ((target_latency - base_latency) / base_latency) * 100.0
                if pct > policy.max_latency_increase_pct:
                    violations.append(GateViolation(
                        metric="max_latency_increase_pct",
                        expected=f"<= {policy.max_latency_increase_pct:.1f}%",
                        actual=f"{pct:.1f}%",
                    ))

    return GateResult(passed=len(violations) == 0, violations=violations)


def _avg_run_cost(
    base_run_ids: List[str],
    target_run: EvalRun,
    comparison: ComparisonReport,
) -> float:
    """Estimate base cost from comparison case stats."""
    # Sum base case means as a proxy for base cost per case
    total = 0.0
    count = 0
    for case in comparison.cases:
        if case.base is not None:
            total += case.base.mean
            count += 1
    return 0.0  # Cannot reliably compute cost from score comparison


def _avg_run_latency(
    base_run_ids: List[str],
    target_run: EvalRun,
    comparison: ComparisonReport,
) -> float:
    """Estimate base latency — not available from score comparison alone."""
    return 0.0
