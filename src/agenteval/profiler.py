"""Performance profiler for AgentEval.

Provides per-case latency/cost analysis, outlier detection, trend analysis,
and actionable recommendations.  Uses stdlib ``statistics`` only.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Dict, List

from agenteval.models import EvalRun


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProfileResult:
    """Per-case profiling result."""
    case_name: str
    latency_ms: int
    cost_usd: float
    is_outlier: bool = False
    z_score: float = 0.0


@dataclass
class SuiteProfile:
    """Aggregate profile for an entire evaluation run."""
    results: List[ProfileResult]
    mean_latency: float = 0.0
    std_latency: float = 0.0
    mean_cost: float = 0.0
    std_cost: float = 0.0
    outlier_count: int = 0
    total_cost: float = 0.0
    recommendations: List[str] = field(default_factory=list)


@dataclass
class TrendResult:
    """Trend analysis across multiple runs."""
    case_trends: Dict[str, str] = field(default_factory=dict)   # case -> improving/degrading/stable
    overall_direction: str = "stable"
    cost_trend: str = "stable"


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------

class Profiler:
    """Analyse a single evaluation run for performance characteristics."""

    def profile_run(self, run: EvalRun) -> SuiteProfile:
        """Compute per-case stats and detect outliers (latency > mean + 2σ)."""
        if not run.results:
            return SuiteProfile(results=[])

        latencies = [r.latency_ms for r in run.results]
        costs = [r.cost_usd or 0.0 for r in run.results]

        mean_lat = statistics.mean(latencies)
        std_lat = statistics.stdev(latencies) if len(latencies) >= 2 else 0.0
        mean_c = statistics.mean(costs)
        std_c = statistics.stdev(costs) if len(costs) >= 2 else 0.0
        total_c = sum(costs)

        profile_results: List[ProfileResult] = []
        outlier_count = 0
        for r in run.results:
            cost = r.cost_usd or 0.0
            z = (r.latency_ms - mean_lat) / std_lat if std_lat > 0 else 0.0
            is_outlier = r.latency_ms > mean_lat + 2 * std_lat if std_lat > 0 else False
            if is_outlier:
                outlier_count += 1
            profile_results.append(ProfileResult(
                case_name=r.case_name,
                latency_ms=r.latency_ms,
                cost_usd=cost,
                is_outlier=is_outlier,
                z_score=z,
            ))

        profile = SuiteProfile(
            results=profile_results,
            mean_latency=mean_lat,
            std_latency=std_lat,
            mean_cost=mean_c,
            std_cost=std_c,
            outlier_count=outlier_count,
            total_cost=total_c,
        )
        profile.recommendations = generate_recommendations(profile)
        return profile


# ---------------------------------------------------------------------------
# Trend analysis (PP-2)
# ---------------------------------------------------------------------------

def trend_analysis(runs: List[EvalRun]) -> TrendResult:
    """Analyse latency/cost trends across ordered runs.

    Trend = (last - first) / first.  >10% increase = degrading, >10% decrease = improving.
    """
    if not runs:
        return TrendResult()

    # Gather per-case latency series (in run order)
    case_latencies: Dict[str, List[int]] = {}
    case_costs: Dict[str, List[float]] = {}
    for run in runs:
        for r in run.results:
            case_latencies.setdefault(r.case_name, []).append(r.latency_ms)
            case_costs.setdefault(r.case_name, []).append(r.cost_usd or 0.0)

    case_trends: Dict[str, str] = {}
    for name, lats in case_latencies.items():
        case_trends[name] = _classify_trend(lats)

    # Overall direction — average of first-run vs last-run latencies
    first_lats = [r.latency_ms for r in runs[0].results] if runs[0].results else [0]
    last_lats = [r.latency_ms for r in runs[-1].results] if runs[-1].results else [0]
    overall = _classify_trend([int(statistics.mean(first_lats)), int(statistics.mean(last_lats))])

    # Cost trend
    run_costs = [sum(r.cost_usd or 0.0 for r in run.results) for run in runs]
    cost_trend = _classify_trend_floats(run_costs)

    return TrendResult(case_trends=case_trends, overall_direction=overall, cost_trend=cost_trend)


def _classify_trend(values: List[int]) -> str:
    if len(values) < 2 or values[0] == 0:
        return "stable"
    change = (values[-1] - values[0]) / values[0]
    if change > 0.10:
        return "degrading"
    if change < -0.10:
        return "improving"
    return "stable"


def _classify_trend_floats(values: List[float]) -> str:
    if len(values) < 2 or values[0] == 0:
        return "stable"
    change = (values[-1] - values[0]) / values[0]
    if change > 0.10:
        return "degrading"
    if change < -0.10:
        return "improving"
    return "stable"


# ---------------------------------------------------------------------------
# Recommendations engine (PP-3)
# ---------------------------------------------------------------------------

def generate_recommendations(profile: SuiteProfile) -> List[str]:
    """Generate actionable recommendations from a suite profile."""
    recs: List[str] = []
    if not profile.results:
        return recs

    mean_lat = profile.mean_latency
    total_cost = profile.total_cost

    for r in profile.results:
        if mean_lat > 0 and r.latency_ms > 3 * mean_lat:
            recs.append(f"Consider caching for '{r.case_name}' — latency {r.latency_ms}ms is >3× average ({mean_lat:.0f}ms)")
        if total_cost > 0 and r.cost_usd > 0.5 * total_cost:
            recs.append(f"Cost hotspot: '{r.case_name}' accounts for {r.cost_usd / total_cost:.0%} of total cost")
        if r.is_outlier:
            recs.append(f"Investigate variability for '{r.case_name}' — flagged as outlier (z={r.z_score:.1f})")

    return recs
