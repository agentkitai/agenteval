"""Agent capability coverage metrics for AgentEval.

Defines capability maps, tracks test coverage, and reports gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from agenteval.models import EvalCase, EvalRun, EvalSuite


@dataclass
class CapabilityCoverage:
    """Coverage information for a single capability."""
    name: str
    test_count: int
    passed_count: int
    failed_count: int
    pass_rate: float
    test_names: List[str] = field(default_factory=list)


@dataclass
class CoverageReport:
    """Complete capability coverage report."""
    total_capabilities: int
    tested_capabilities: int
    untested_capabilities: int
    coverage_pct: float
    capabilities: List[CapabilityCoverage]
    untested: List[str]
    summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoverageConfig:
    """Configuration for coverage checks."""
    declared_capabilities: List[str] = field(default_factory=list)
    min_coverage_pct: float = 0.0  # Minimum coverage to pass (0 = no enforcement)
    capability_field: str = "capabilities"  # Field name in test case tags/config


def extract_capabilities(case: EvalCase) -> Set[str]:
    """Extract capability tags from an eval case.

    Looks for capabilities in:
    1. case.grader_config.get("capabilities")
    2. case.tags with "cap:" prefix
    """
    caps: Set[str] = set()

    # From grader_config
    config_caps = case.grader_config.get("capabilities", [])
    if isinstance(config_caps, list):
        caps.update(config_caps)
    elif isinstance(config_caps, str):
        caps.add(config_caps)

    # From tags with "cap:" prefix
    for tag in case.tags:
        if tag.startswith("cap:"):
            caps.add(tag[4:])

    return caps


def compute_coverage(
    run: EvalRun,
    suite: EvalSuite,
    config: Optional[CoverageConfig] = None,
) -> CoverageReport:
    """Compute capability coverage from eval results.

    Args:
        run: The eval run with results.
        suite: The eval suite with case definitions.
        config: Coverage configuration with declared capabilities.

    Returns:
        CoverageReport with coverage stats.
    """
    if config is None:
        config = CoverageConfig()

    # Build map: case_name -> capabilities
    case_caps: Dict[str, Set[str]] = {}
    for case in suite.cases:
        caps = extract_capabilities(case)
        if caps:
            case_caps[case.name] = caps

    # Build result map: case_name -> passed
    result_map: Dict[str, bool] = {r.case_name: r.passed for r in run.results}

    # Aggregate by capability
    cap_data: Dict[str, Dict[str, Any]] = {}
    all_tested_caps: Set[str] = set()

    for case_name, caps in case_caps.items():
        passed = result_map.get(case_name, False)
        for cap in caps:
            all_tested_caps.add(cap)
            if cap not in cap_data:
                cap_data[cap] = {"test_count": 0, "passed": 0, "failed": 0, "tests": []}
            cap_data[cap]["test_count"] += 1
            cap_data[cap]["tests"].append(case_name)
            if passed:
                cap_data[cap]["passed"] += 1
            else:
                cap_data[cap]["failed"] += 1

    # Build coverage list
    capabilities = []
    for cap_name, data in sorted(cap_data.items()):
        total = data["test_count"]
        pr = data["passed"] / total if total > 0 else 0.0
        capabilities.append(CapabilityCoverage(
            name=cap_name,
            test_count=total,
            passed_count=data["passed"],
            failed_count=data["failed"],
            pass_rate=pr,
            test_names=data["tests"],
        ))

    # Compute untested capabilities
    declared = set(config.declared_capabilities)
    all_caps = declared | all_tested_caps
    untested = sorted(all_caps - all_tested_caps)

    total_caps = len(all_caps)
    tested_caps = len(all_tested_caps)
    coverage_pct = (tested_caps / total_caps * 100) if total_caps > 0 else 100.0

    return CoverageReport(
        total_capabilities=total_caps,
        tested_capabilities=tested_caps,
        untested_capabilities=len(untested),
        coverage_pct=coverage_pct,
        capabilities=capabilities,
        untested=untested,
        summary={
            "total": total_caps,
            "tested": tested_caps,
            "untested": len(untested),
            "coverage_pct": coverage_pct,
        },
    )


def check_coverage_threshold(
    report: CoverageReport,
    min_coverage_pct: float = 0.0,
) -> bool:
    """Check if coverage meets the minimum threshold.

    Args:
        report: Coverage report.
        min_coverage_pct: Minimum coverage percentage (0-100).

    Returns:
        True if coverage is sufficient.
    """
    if min_coverage_pct <= 0:
        return True
    return report.coverage_pct >= min_coverage_pct


def format_coverage_report(report: CoverageReport) -> str:
    """Format a coverage report as human-readable text."""
    lines = [
        f"Capability Coverage: {report.coverage_pct:.0f}%",
        f"Tested: {report.tested_capabilities}/{report.total_capabilities} capabilities",
        "",
    ]

    if report.capabilities:
        lines.append(f"{'Capability':<25} {'Tests':>6} {'Pass Rate':>10}")
        lines.append("-" * 45)
        for cap in report.capabilities:
            lines.append(f"  {cap.name:<23} {cap.test_count:>6} {cap.pass_rate:>9.0%}")

    if report.untested:
        lines.extend(["", "⚠ Untested capabilities:"])
        for cap in report.untested:
            lines.append(f"  • {cap}")

    return "\n".join(lines)


def gap_analysis(
    suite: EvalSuite,
    declared_capabilities: List[str],
) -> Dict[str, Any]:
    """Compare declared capabilities against tested ones.

    Args:
        suite: The eval suite.
        declared_capabilities: List of capabilities the agent claims to have.

    Returns:
        Dict with gap analysis results.
    """
    tested: Set[str] = set()
    for case in suite.cases:
        tested.update(extract_capabilities(case))

    declared = set(declared_capabilities)
    untested = sorted(declared - tested)
    undeclared = sorted(tested - declared)

    return {
        "declared": sorted(declared),
        "tested": sorted(tested),
        "untested_capabilities": untested,
        "undeclared_tested": undeclared,
        "coverage_pct": (len(tested & declared) / len(declared) * 100) if declared else 100.0,
        "warnings": [f"Capability '{c}' has no test coverage" for c in untested],
    }
