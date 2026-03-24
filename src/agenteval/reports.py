"""Unified run report generation for AgentEval."""

from __future__ import annotations

import json
from typing import Any, Dict

from agenteval.models import EvalRun


def generate_json_report(run: EvalRun) -> Dict[str, Any]:
    """Generate a machine-readable report dictionary."""
    return {
        "version": "1.0",
        "run_id": run.id,
        "suite": run.suite,
        "created_at": run.created_at,
        "summary": run.summary,
        "config": run.config,
        "results": [
            {
                "case_name": r.case_name,
                "passed": r.passed,
                "score": r.score,
                "latency_ms": r.latency_ms,
                "details": r.details,
            }
            for r in run.results
        ],
    }


def generate_markdown_report(run: EvalRun) -> str:
    """Generate a human-readable markdown report."""
    s = run.summary
    lines = [
        f"# Eval Report: {run.suite}",
        "",
        f"**Run ID:** `{run.id}`  ",
        f"**Created:** {run.created_at}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total | {s.get('total', 0)} |",
        f"| Passed | {s.get('passed', 0)} |",
        f"| Failed | {s.get('failed', 0)} |",
        f"| Pass Rate | {s.get('pass_rate', 0):.0%} |",
    ]

    if s.get("total_cost_usd"):
        lines.append(f"| Cost | ${s['total_cost_usd']:.4f} |")
    if s.get("avg_latency_ms"):
        lines.append(f"| Avg Latency | {s['avg_latency_ms']:.0f}ms |")

    lines.extend(["", "## Results", ""])
    lines.append("| Case | Status | Score | Latency |")
    lines.append("|------|--------|-------|---------|")

    failed_cases = []
    for r in run.results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"| {r.case_name} | {status} | {r.score:.2f} | {r.latency_ms}ms |")
        if not r.passed:
            failed_cases.append(r)

    if failed_cases:
        lines.extend(["", "## Failed Cases", ""])
        for r in failed_cases:
            lines.append(f"### {r.case_name}")
            lines.append("")
            if r.details:
                for k, v in r.details.items():
                    lines.append(f"- **{k}:** {v}")
            lines.append("")

    return "\n".join(lines) + "\n"


def generate_report(run: EvalRun, format: str = "json") -> str:
    """Generate a report in the specified format.

    Args:
        run: The evaluation run to report on.
        format: Either 'json' or 'markdown'.

    Returns:
        The report as a string.
    """
    if format == "markdown":
        return generate_markdown_report(run)
    return json.dumps(generate_json_report(run), indent=2) + "\n"
