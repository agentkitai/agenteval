"""Flaky test detection for non-deterministic LLM outputs.

Supports multi-run mode, quarantine, and statistical pass criteria.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agenteval.models import EvalResult


@dataclass
class MultiRunResult:
    """Aggregated result for a test case across multiple runs."""
    case_name: str
    runs: int
    passed_count: int
    pass_rate: float
    mean_score: float
    stddev_score: float
    scores: List[float]
    consistency_score: float
    is_flaky: bool
    quarantined: bool = False


@dataclass
class MultiRunReport:
    """Report for all cases across multiple runs."""
    cases: List[MultiRunResult]
    total_runs_per_case: int
    flaky_count: int
    quarantined_count: int
    summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QuarantineConfig:
    """Configuration for flaky test quarantine."""
    min_fail_rate: float = 0.3   # Fail rate above this = potentially flaky
    max_fail_rate: float = 0.7   # Fail rate below this = potentially flaky (above = just broken)
    min_runs: int = 3            # Minimum runs before quarantine decision


def aggregate_multi_run(
    case_name: str,
    results: List[EvalResult],
) -> MultiRunResult:
    """Aggregate results from multiple runs of the same test case."""
    n = len(results)
    if n == 0:
        return MultiRunResult(
            case_name=case_name, runs=0, passed_count=0, pass_rate=0.0,
            mean_score=0.0, stddev_score=0.0, scores=[], consistency_score=0.0,
            is_flaky=False,
        )

    passed_count = sum(1 for r in results if r.passed)
    scores = [r.score for r in results]
    pass_rate = passed_count / n

    mean_score = sum(scores) / n
    if n >= 2:
        variance = sum((s - mean_score) ** 2 for s in scores) / (n - 1)
        stddev = math.sqrt(variance)
    else:
        stddev = 0.0

    # Consistency: 1.0 = all same result, 0.0 = max variance
    # Based on how close pass_rate is to 0 or 1
    consistency_score = 1.0 - 4 * pass_rate * (1 - pass_rate)  # peaks at 0 or 1
    consistency_score = max(0.0, consistency_score)

    # Flaky if not all pass and not all fail
    is_flaky = 0 < passed_count < n

    return MultiRunResult(
        case_name=case_name,
        runs=n,
        passed_count=passed_count,
        pass_rate=pass_rate,
        mean_score=mean_score,
        stddev_score=stddev,
        scores=scores,
        consistency_score=consistency_score,
        is_flaky=is_flaky,
    )


def should_quarantine(
    result: MultiRunResult,
    config: Optional[QuarantineConfig] = None,
) -> bool:
    """Determine if a test should be quarantined based on its multi-run results.

    A test is quarantined when:
    - It has enough runs (>= min_runs)
    - Its failure rate is between min_fail_rate and max_fail_rate
    """
    if config is None:
        config = QuarantineConfig()

    if result.runs < config.min_runs:
        return False

    fail_rate = 1.0 - result.pass_rate
    return config.min_fail_rate <= fail_rate <= config.max_fail_rate


def check_statistical_pass(
    result: MultiRunResult,
    required_pass_rate: float = 0.8,
) -> bool:
    """Check if a test passes using statistical pass criteria.

    Instead of binary pass/fail, passes if >= required_pass_rate of N runs succeed.
    """
    return result.pass_rate >= required_pass_rate


def build_multi_run_report(
    all_results: Dict[str, List[EvalResult]],
    num_runs: int,
    quarantine_config: Optional[QuarantineConfig] = None,
) -> MultiRunReport:
    """Build a complete multi-run report from grouped results.

    Args:
        all_results: Dict mapping case_name -> list of EvalResult from all runs.
        num_runs: Number of runs performed per case.
        quarantine_config: Quarantine configuration.
    """
    cases = []
    flaky_count = 0
    quarantined_count = 0

    for case_name, results in all_results.items():
        mr = aggregate_multi_run(case_name, results)
        mr.quarantined = should_quarantine(mr, quarantine_config)

        if mr.is_flaky:
            flaky_count += 1
        if mr.quarantined:
            quarantined_count += 1
        cases.append(mr)

    return MultiRunReport(
        cases=cases,
        total_runs_per_case=num_runs,
        flaky_count=flaky_count,
        quarantined_count=quarantined_count,
        summary={
            "total_cases": len(cases),
            "flaky_cases": flaky_count,
            "quarantined_cases": quarantined_count,
            "stable_cases": len(cases) - flaky_count,
        },
    )
