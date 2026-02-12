"""Statistical comparison engine for AgentEval.

Provides Welch's t-test, regression detection, and multi-run group comparison.
Uses scipy.stats if available, otherwise pure Python fallback.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from agenteval.models import EvalRun


class ChangeStatus(Enum):
    """Status of a case between two run groups."""
    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"
    NEW = "new"
    REMOVED = "removed"


@dataclass
class CaseStats:
    """Descriptive statistics for a single case across runs."""
    case_name: str
    n: int
    mean: float
    stddev: float
    scores: List[float]


@dataclass
class CaseComparison:
    """Statistical comparison of a single case between two groups."""
    case_name: str
    status: ChangeStatus
    base: Optional[CaseStats]
    target: Optional[CaseStats]
    mean_diff: float = 0.0
    t_stat: float = 0.0
    p_value: float = 1.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    significant: bool = False


@dataclass
class ComparisonReport:
    """Full comparison report between two groups of runs."""
    base_run_ids: List[str]
    target_run_ids: List[str]
    cases: List[CaseComparison]
    summary: Dict[str, int] = field(default_factory=dict)
    alpha: float = 0.05
    regression_threshold: float = 0.0

    @property
    def regressions(self) -> List[CaseComparison]:
        return [c for c in self.cases if c.status == ChangeStatus.REGRESSED]

    @property
    def improvements(self) -> List[CaseComparison]:
        return [c for c in self.cases if c.status == ChangeStatus.IMPROVED]


def _clean_scores(scores: Sequence[float]) -> List[float]:
    """Remove NaN/inf values from scores."""
    return [s for s in scores if math.isfinite(s)]


def compute_stats(case_name: str, scores: Sequence[float]) -> CaseStats:
    """Compute descriptive statistics for a list of scores."""
    clean = _clean_scores(scores)
    n = len(clean)
    if n == 0:
        return CaseStats(case_name=case_name, n=0, mean=0.0, stddev=0.0, scores=[])
    mean = sum(clean) / n
    if n < 2:
        stddev = 0.0
    else:
        variance = sum((x - mean) ** 2 for x in clean) / (n - 1)
        stddev = math.sqrt(variance)
    return CaseStats(case_name=case_name, n=n, mean=mean, stddev=stddev, scores=list(clean))


def _welch_t_test_scipy(
    mean1: float, std1: float, n1: int,
    mean2: float, std2: float, n2: int,
) -> Tuple[float, float]:
    """Use scipy for Welch's t-test if available."""
    from scipy import stats  # type: ignore[import-untyped]
    # Build fake samples with exact mean/std is fragile; use ttest_ind_from_stats
    t_stat, p_value = stats.ttest_ind_from_stats(
        mean1, std1, n1, mean2, std2, n2, equal_var=False,
    )
    return float(t_stat), float(p_value)


def _welch_degrees_of_freedom(s1: float, n1: int, s2: float, n2: int) -> float:
    """Welch-Satterthwaite degrees of freedom."""
    if n1 < 2 or n2 < 2:
        return 0.0
    v1 = s1 ** 2 / n1
    v2 = s2 ** 2 / n2
    num = (v1 + v2) ** 2
    denom = v1 ** 2 / (n1 - 1) + v2 ** 2 / (n2 - 1)
    if denom == 0:
        return 0.0
    return num / denom


def _t_cdf_approx(t: float, df: float) -> float:
    """Approximate the CDF of the t-distribution using the normal approximation
    for large df, and a crude beta-function-based approximation otherwise.

    This is a pure-Python fallback when scipy is unavailable.
    Uses the approximation: P(T <= t) ≈ Φ(t * (1 - 1/(4*df)))
    which is reasonable for df > 2.
    """
    if df <= 0:
        return 0.5
    # For very large df, t-distribution ≈ normal
    # Use improved approximation
    x = t * (1.0 - 1.0 / (4.0 * df))
    # Standard normal CDF via error function
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _welch_t_test_pure(
    mean1: float, std1: float, n1: int,
    mean2: float, std2: float, n2: int,
) -> Tuple[float, float]:
    """Pure Python Welch's t-test (fallback)."""
    se = math.sqrt(std1 ** 2 / n1 + std2 ** 2 / n2)
    if se == 0:
        return 0.0, 1.0
    t_stat = (mean1 - mean2) / se
    df = _welch_degrees_of_freedom(std1, n1, std2, n2)
    if df < 1:
        return t_stat, 1.0
    # Two-tailed p-value
    p_value = 2.0 * (1.0 - _t_cdf_approx(abs(t_stat), df))
    p_value = max(0.0, min(1.0, p_value))
    return t_stat, p_value


def welch_t_test(
    mean1: float, std1: float, n1: int,
    mean2: float, std2: float, n2: int,
) -> Tuple[float, float]:
    """Perform Welch's t-test. Returns (t_statistic, p_value).

    Uses scipy if available, otherwise pure Python fallback.
    Requires n1 >= 2 and n2 >= 2 for meaningful results.
    """
    if n1 < 2 or n2 < 2:
        return 0.0, 1.0
    # Special case: both have zero variance
    # If means differ, it's a deterministic difference (p≈0).
    # If means are equal, no difference (p=1).
    _EPS = 1e-15
    if std1 < _EPS and std2 < _EPS:
        if abs(mean1 - mean2) < _EPS:
            return 0.0, 1.0
        return float("inf") if mean1 > mean2 else float("-inf"), 0.0
    try:
        t_stat, p_value = _welch_t_test_scipy(mean1, std1, n1, mean2, std2, n2)
        # scipy can return NaN for degenerate cases (e.g., one std=0)
        if math.isnan(p_value):
            return _welch_t_test_pure(mean1, std1, n1, mean2, std2, n2)
        return t_stat, p_value
    except ImportError:
        return _welch_t_test_pure(mean1, std1, n1, mean2, std2, n2)


def confidence_interval(
    mean1: float, std1: float, n1: int,
    mean2: float, std2: float, n2: int,
    alpha: float = 0.05,
) -> Tuple[float, float]:
    """Compute confidence interval for the difference in means (mean1 - mean2).

    Returns (lower, upper) bounds.
    """
    diff = mean1 - mean2
    if n1 < 2 or n2 < 2:
        return diff, diff
    if std1 < 1e-15 and std2 < 1e-15:
        return diff, diff

    se = math.sqrt(std1 ** 2 / n1 + std2 ** 2 / n2)
    df = _welch_degrees_of_freedom(std1, n1, std2, n2)

    # Get t critical value
    try:
        from scipy import stats  # type: ignore[import-untyped]
        t_crit = stats.t.ppf(1.0 - alpha / 2.0, df)
    except ImportError:
        # Approximate: for df > 30, t ≈ z; for smaller df use rough table
        if df >= 120:
            t_crit = 1.96
        elif df >= 30:
            t_crit = 2.0
        elif df >= 10:
            t_crit = 2.23
        elif df >= 5:
            t_crit = 2.57
        else:
            t_crit = 2.78

    diff = mean1 - mean2
    margin = t_crit * se
    return diff - margin, diff + margin


def _gather_case_scores(runs: Sequence[EvalRun]) -> Dict[str, List[float]]:
    """Gather scores per case across multiple runs."""
    scores: Dict[str, List[float]] = {}
    for run in runs:
        for result in run.results:
            scores.setdefault(result.case_name, []).append(result.score)
    return scores


def compare_runs(
    base_runs: Sequence[EvalRun],
    target_runs: Sequence[EvalRun],
    alpha: float = 0.05,
    regression_threshold: float = 0.0,
) -> ComparisonReport:
    """Compare two groups of runs and detect regressions.

    Args:
        base_runs: The baseline group of runs.
        target_runs: The target/new group of runs.
        alpha: Significance level for the t-test.
        regression_threshold: Minimum score drop to consider a regression
            (in addition to statistical significance). Default 0.0 means
            any statistically significant drop is a regression.

    Returns:
        ComparisonReport with per-case comparisons.
    """
    base_scores = _gather_case_scores(base_runs)
    target_scores = _gather_case_scores(target_runs)

    all_cases = list(dict.fromkeys(list(base_scores) + list(target_scores)))

    comparisons: List[CaseComparison] = []
    summary = {"improved": 0, "regressed": 0, "unchanged": 0, "new": 0, "removed": 0}

    for case_name in all_cases:
        b_scores = base_scores.get(case_name)
        t_scores = target_scores.get(case_name)

        if b_scores is None:
            # New case
            t_stats = compute_stats(case_name, t_scores)  # type: ignore[arg-type]
            comp = CaseComparison(
                case_name=case_name, status=ChangeStatus.NEW,
                base=None, target=t_stats,
            )
            summary["new"] += 1
        elif t_scores is None:
            # Removed case
            b_stats = compute_stats(case_name, b_scores)
            comp = CaseComparison(
                case_name=case_name, status=ChangeStatus.REMOVED,
                base=b_stats, target=None,
            )
            summary["removed"] += 1
        else:
            b_stats = compute_stats(case_name, b_scores)
            t_stats = compute_stats(case_name, t_scores)
            mean_diff = t_stats.mean - b_stats.mean

            t_stat, p_value = welch_t_test(
                b_stats.mean, b_stats.stddev, b_stats.n,
                t_stats.mean, t_stats.stddev, t_stats.n,
            )
            ci_lo, ci_hi = confidence_interval(
                t_stats.mean, t_stats.stddev, t_stats.n,
                b_stats.mean, b_stats.stddev, b_stats.n,
                alpha=alpha,
            )

            significant = p_value < alpha

            # Determine status
            if significant and mean_diff < -regression_threshold:
                status = ChangeStatus.REGRESSED
            elif significant and mean_diff > regression_threshold:
                status = ChangeStatus.IMPROVED
            else:
                status = ChangeStatus.UNCHANGED

            comp = CaseComparison(
                case_name=case_name, status=status,
                base=b_stats, target=t_stats,
                mean_diff=mean_diff, t_stat=t_stat, p_value=p_value,
                ci_lower=ci_lo, ci_upper=ci_hi, significant=significant,
            )
            summary[status.value] += 1

        comparisons.append(comp)

    return ComparisonReport(
        base_run_ids=[r.id for r in base_runs],
        target_run_ids=[r.id for r in target_runs],
        cases=comparisons,
        summary=summary,
        alpha=alpha,
        regression_threshold=regression_threshold,
    )
