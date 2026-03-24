"""GitHub PR comment formatter — markdown table with summary."""

from __future__ import annotations

from agenteval.ci import CIResult
from agenteval.models import EvalRun

MARKER = "<!-- agenteval-results -->"


def format_github_comment(ci_result: CIResult, run: EvalRun) -> str:
    """Format CI result as a GitHub PR comment with markdown table."""
    badge = "\u2705" if ci_result.passed else "\u274c"
    status = "Passed" if ci_result.passed else "Failed"
    lines = [
        MARKER,
        "## \U0001f9ea AgentEval Results",
        "",
        f"{badge} **{status}** ({ci_result.pass_rate:.0%} pass rate, "
        f"{ci_result.regression_count} regressions)",
        "",
    ]

    # Regressions section above the fold
    if ci_result.regressions:
        lines.append("### \u26a0\ufe0f Regressions")
        for name in ci_result.regressions:
            lines.append(f"- **{name}**")
        lines.append("")

    # Detailed results in collapsible section
    table_lines = [
        "| Case | Status | Score | Latency | Cost |",
        "|------|--------|-------|---------|------|",
    ]

    for r in run.results:
        status_icon = "\u2713" if r.passed else "\u2717"
        cost = f"${r.cost_usd:.4f}" if r.cost_usd else "\u2014"
        table_lines.append(
            f"| {r.case_name} | {status_icon} | {r.score:.2f} | {r.latency_ms}ms | {cost} |"
        )

    case_count = len(run.results)
    lines.append(f"<details><summary>\U0001f4cb Full Results ({case_count} cases)</summary>")
    lines.append("")
    lines.extend(table_lines)
    lines.append("")
    lines.append("</details>")

    return "\n".join(lines) + "\n"
