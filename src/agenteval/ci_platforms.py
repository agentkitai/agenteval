"""Multi-CI platform support for AgentEval.

Supports GitHub Actions, GitLab CI, CircleCI, and Jenkins.
Auto-detects CI environment and provides platform-specific integrations.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from agenteval.badge import generate_badge
from agenteval.models import EvalRun


class CIPlatform(Enum):
    """Supported CI platforms."""
    GITHUB = "github"
    GITLAB = "gitlab"
    CIRCLECI = "circleci"
    JENKINS = "jenkins"
    UNKNOWN = "unknown"


@dataclass
class CIEnvironment:
    """Detected CI environment information."""
    platform: CIPlatform
    branch: str = ""
    commit_sha: str = ""
    pr_number: Optional[int] = None
    repo: str = ""
    build_url: str = ""
    env_vars: Dict[str, str] = field(default_factory=dict)


def detect_ci_platform() -> CIEnvironment:
    """Auto-detect the CI platform from environment variables."""
    if os.environ.get("GITHUB_ACTIONS"):
        return CIEnvironment(
            platform=CIPlatform.GITHUB,
            branch=os.environ.get("GITHUB_REF_NAME", ""),
            commit_sha=os.environ.get("GITHUB_SHA", ""),
            repo=os.environ.get("GITHUB_REPOSITORY", ""),
            build_url=f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        )

    if os.environ.get("GITLAB_CI"):
        pr_number = None
        mr_iid = os.environ.get("CI_MERGE_REQUEST_IID")
        if mr_iid:
            try:
                pr_number = int(mr_iid)
            except ValueError:
                pass
        return CIEnvironment(
            platform=CIPlatform.GITLAB,
            branch=os.environ.get("CI_COMMIT_BRANCH", os.environ.get("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", "")),
            commit_sha=os.environ.get("CI_COMMIT_SHA", ""),
            pr_number=pr_number,
            repo=os.environ.get("CI_PROJECT_PATH", ""),
            build_url=os.environ.get("CI_PIPELINE_URL", ""),
        )

    if os.environ.get("CIRCLECI"):
        pr_number = None
        pr_str = os.environ.get("CIRCLE_PR_NUMBER")
        if pr_str:
            try:
                pr_number = int(pr_str)
            except ValueError:
                pass
        return CIEnvironment(
            platform=CIPlatform.CIRCLECI,
            branch=os.environ.get("CIRCLE_BRANCH", ""),
            commit_sha=os.environ.get("CIRCLE_SHA1", ""),
            pr_number=pr_number,
            repo=f"{os.environ.get('CIRCLE_PROJECT_USERNAME', '')}/{os.environ.get('CIRCLE_PROJECT_REPONAME', '')}",
            build_url=os.environ.get("CIRCLE_BUILD_URL", ""),
        )

    if os.environ.get("JENKINS_URL"):
        return CIEnvironment(
            platform=CIPlatform.JENKINS,
            branch=os.environ.get("GIT_BRANCH", os.environ.get("BRANCH_NAME", "")),
            commit_sha=os.environ.get("GIT_COMMIT", ""),
            repo=os.environ.get("JOB_NAME", ""),
            build_url=os.environ.get("BUILD_URL", ""),
        )

    return CIEnvironment(platform=CIPlatform.UNKNOWN)


def format_gitlab_comment(run: EvalRun) -> str:
    """Format eval results as a GitLab MR comment (Markdown)."""
    s = run.summary
    status = "✅ PASSED" if s.get("failed", 0) == 0 else "❌ FAILED"

    lines = [
        f"## AgentEval Results: {status}",
        "",
        f"**Suite:** {run.suite} | **Run:** {run.id}",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Pass Rate | {s.get('pass_rate', 0):.0%} |",
        f"| Passed | {s.get('passed', 0)} |",
        f"| Failed | {s.get('failed', 0)} |",
        f"| Total | {s.get('total', 0)} |",
    ]

    if s.get("total_cost_usd"):
        lines.append(f"| Cost | ${s['total_cost_usd']:.4f} |")
    if s.get("avg_latency_ms"):
        lines.append(f"| Avg Latency | {s['avg_latency_ms']:.0f}ms |")

    failed = [r for r in run.results if not r.passed]
    if failed:
        lines.extend(["", "### Failed Cases", ""])
        for r in failed[:20]:
            reason = r.details.get("reason", "")
            lines.append(f"- **{r.case_name}**: {reason}")

    lines.append(f"\n<!-- agenteval-run-{run.id} -->")
    return "\n".join(lines)


def post_gitlab_mr_comment(
    run: EvalRun,
    project_id: Optional[str] = None,
    mr_iid: Optional[int] = None,
    token: Optional[str] = None,
    server_url: str = "https://gitlab.com",
) -> bool:
    """Post eval results as a comment on a GitLab MR.

    Returns True on success, False on failure.
    """
    project_id = project_id or os.environ.get("CI_PROJECT_ID")
    token = token or os.environ.get("GITLAB_TOKEN", os.environ.get("CI_JOB_TOKEN"))

    if mr_iid is None:
        mr_str = os.environ.get("CI_MERGE_REQUEST_IID")
        if mr_str:
            try:
                mr_iid = int(mr_str)
            except ValueError:
                return False

    if not all([project_id, mr_iid, token]):
        return False

    comment = format_gitlab_comment(run)
    url = f"{server_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes"

    try:
        resp = httpx.post(
            url,
            json={"body": comment},
            headers={"PRIVATE-TOKEN": token},
            timeout=10.0,
        )
        return 200 <= resp.status_code < 300
    except Exception:
        return False


def format_circleci_results(run: EvalRun) -> Dict[str, Any]:
    """Format eval results in CircleCI-compatible test format."""
    tests = []
    for r in run.results:
        tests.append({
            "name": r.case_name,
            "classname": run.suite,
            "result": "success" if r.passed else "failure",
            "message": r.details.get("reason", ""),
            "run_time": r.latency_ms / 1000.0,
        })

    return {
        "tests": tests,
        "summary": {
            "total": run.summary.get("total", 0),
            "passed": run.summary.get("passed", 0),
            "failed": run.summary.get("failed", 0),
        },
    }


def generate_jenkins_html_report(run: EvalRun) -> str:
    """Generate a Jenkins-native HTML report."""
    s = run.summary
    status_color = "#4caf50" if s.get("failed", 0) == 0 else "#f44336"
    status = "PASSED" if s.get("failed", 0) == 0 else "FAILED"

    rows = []
    for r in run.results:
        color = "#4caf50" if r.passed else "#f44336"
        status_text = "PASS" if r.passed else "FAIL"
        reason = r.details.get("reason", "")
        rows.append(
            f'<tr><td>{r.case_name}</td><td style="color:{color}">{status_text}</td>'
            f'<td>{r.score:.2f}</td><td>{r.latency_ms}ms</td><td>{reason}</td></tr>'
        )

    return f"""<!DOCTYPE html>
<html>
<head><title>AgentEval Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #f5f5f5; }}
.header {{ padding: 10px; color: white; background-color: {status_color}; border-radius: 4px; }}
</style></head>
<body>
<div class="header"><h1>AgentEval: {status}</h1></div>
<p><strong>Suite:</strong> {run.suite} | <strong>Run:</strong> {run.id} | <strong>Created:</strong> {run.created_at[:19]}</p>
<h2>Summary</h2>
<p>Pass Rate: {s.get('pass_rate', 0):.0%} | Passed: {s.get('passed', 0)} | Failed: {s.get('failed', 0)} | Total: {s.get('total', 0)}</p>
<h2>Results</h2>
<table>
<tr><th>Case</th><th>Status</th><th>Score</th><th>Latency</th><th>Details</th></tr>
{"".join(rows)}
</table>
</body></html>"""
