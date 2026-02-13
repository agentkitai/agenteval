"""GitHub PR comment formatter — markdown table with summary."""

from __future__ import annotations

from agenteval.ci import CIResult
from agenteval.models import EvalRun

MARKER = "<!-- agenteval-results -->"


def format_github_comment(ci_result: CIResult, run: EvalRun) -> str:
    """Format CI result as a GitHub PR comment with markdown table."""
    badge = "✅" if ci_result.passed else "❌"
    status = "Passed" if ci_result.passed else "Failed"
    lines = [
        MARKER,
        f"## 🧪 AgentEval Results",
        "",
        f"{badge} **{status}** ({ci_result.pass_rate:.0%} pass rate, "
        f"{ci_result.regression_count} regressions)",
        "",
        "| Case | Status | Score | Latency | Cost |",
        "|------|--------|-------|---------|------|",
    ]

    for r in run.results:
        status_icon = "✓" if r.passed else "✗"
        cost = f"${r.cost_usd:.4f}" if r.cost_usd else "—"
        lines.append(
            f"| {r.case_name} | {status_icon} | {r.score:.2f} | {r.latency_ms}ms | {cost} |"
        )

    if ci_result.regressions:
        lines.append("")
        lines.append("### ⚠️ Regressions")
        for name in ci_result.regressions:
            lines.append(f"- **{name}**")

    return "\n".join(lines) + "\n"
