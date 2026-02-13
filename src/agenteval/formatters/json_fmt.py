"""JSON output formatter for CI results."""

from __future__ import annotations

import json

from agenteval.ci import CIResult
from agenteval.models import EvalRun


def format_json(ci_result: CIResult, run: EvalRun) -> str:
    """Format CI result and run as JSON string."""
    passed_count = sum(1 for r in run.results if r.passed)
    total = len(run.results)

    results = []
    for r in run.results:
        results.append({
            "case_name": r.case_name,
            "passed": r.passed,
            "score": r.score,
            "latency_ms": r.latency_ms,
        })

    output = {
        "passed": ci_result.passed,
        "pass_rate": ci_result.pass_rate,
        "total": total,
        "passed_count": passed_count,
        "failed_count": total - passed_count,
        "regressions": ci_result.regressions,
        "results": results,
    }
    return json.dumps(output, indent=2)
