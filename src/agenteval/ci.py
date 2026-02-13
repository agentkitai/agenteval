"""CI integration — threshold checks and regression detection for AgentEval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from agenteval.models import EvalRun


@dataclass
class CIConfig:
    """Configuration for CI threshold checks."""
    min_pass_rate: float = 0.8
    max_regression_pct: float = 10.0
    baseline_run: Optional[str] = None


@dataclass
class CIResult:
    """Result of a CI threshold check."""
    passed: bool
    pass_rate: float
    regression_count: int
    regression_pct: float
    regressions: List[str] = field(default_factory=list)
    summary: str = ""


def detect_regressions(current: EvalRun, baseline: EvalRun) -> List[str]:
    """Detect cases that passed in baseline but failed in current.

    New cases (not in baseline) are NOT regressions.
    """
    baseline_passed = {
        r.case_name for r in baseline.results if r.passed
    }
    regressions = []
    for r in current.results:
        if r.case_name in baseline_passed and not r.passed:
            regressions.append(r.case_name)
    return regressions


def check_thresholds(run: EvalRun, config: CIConfig, baseline: Optional[EvalRun] = None) -> CIResult:
    """Check if a run meets CI thresholds.

    Pass when pass_rate >= min_pass_rate AND regression_pct <= max_regression_pct.
    """
    total = len(run.results)
    passed_count = sum(1 for r in run.results if r.passed)
    pass_rate = passed_count / total if total > 0 else 0.0

    regressions: List[str] = []
    if baseline is not None:
        regressions = detect_regressions(run, baseline)

    regression_count = len(regressions)
    regression_pct = (regression_count / total * 100) if total > 0 else 0.0

    rate_ok = pass_rate >= config.min_pass_rate
    regression_ok = regression_pct <= config.max_regression_pct

    ci_passed = rate_ok and regression_ok

    parts = []
    parts.append(f"Pass rate: {pass_rate:.0%} (threshold: {config.min_pass_rate:.0%})")
    if regressions:
        parts.append(f"Regressions: {regression_count} ({regression_pct:.1f}%) — {', '.join(regressions)}")
    parts.append("CI: PASSED" if ci_passed else "CI: FAILED")

    return CIResult(
        passed=ci_passed,
        pass_rate=pass_rate,
        regression_count=regression_count,
        regression_pct=regression_pct,
        regressions=regressions,
        summary=". ".join(parts),
    )
