"""EU AI Act testing-evidence module (#8).

Maps an :class:`~agenteval.models.EvalRun` onto a structured **testing-evidence**
document aligned with EU AI Act Art. 11 / Annex IV §6 (the *testing &
validation* slice of the technical documentation) — identity-bound (to the agent
under test) and **tamper-evident** via a SHA-256 content hash.

This is deliberately NOT "a conformity certificate": notified bodies certify
conformity. This produces the verifiable testing-evidence artifact a GRC tool or
auditor references. The content hash lets the same artifact be anchored into
AgentLens's hash chain (the cross-product evidence story, agentlens#98) without
this module depending on AgentLens.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from agenteval.models import EvalRun

EVIDENCE_KIND = "agenteval.eu-ai-act-testing-evidence/v1"
STANDARD = "EU AI Act Art. 11 / Annex IV §6 (testing & validation)"


def _canonical(obj: Any) -> str:
    """Deterministic JSON (sorted keys) so the content hash is reproducible."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _graders(run: EvalRun) -> list[str]:
    seen: list[str] = []
    for r in run.results:
        g = r.details.get("grader") if isinstance(r.details, dict) else None
        if isinstance(g, str) and g not in seen:
            seen.append(g)
    return sorted(seen)


def build_testing_evidence(run: EvalRun, *, agent_id: Optional[str] = None) -> dict[str, Any]:
    """Build the Art.11/Annex-IV testing-evidence document for one eval run.

    ``agent_id`` overrides the bound identity (defaults to ``run.agent_ref``).
    The returned dict carries a ``contentHash`` (``sha256:…``) computed over the
    canonicalized body, so any later modification is detectable.
    """
    summary = run.summary if isinstance(run.summary, dict) else {}
    total = int(summary.get("total", len(run.results)))
    passed = int(summary.get("passed", sum(1 for r in run.results if r.passed)))
    failed = int(summary.get("failed", total - passed))
    pass_rate = summary.get("pass_rate")
    if pass_rate is None:
        pass_rate = (passed / total) if total else None

    body: dict[str, Any] = {
        "kind": EVIDENCE_KIND,
        "standard": STANDARD,
        "subject": {
            "agentId": agent_id or run.agent_ref,
            "suite": run.suite,
        },
        "run": {"id": run.id, "createdAt": run.created_at},
        "testingMethodology": {
            "suite": run.suite,
            "graders": _graders(run),
            "caseCount": total,
            "config": run.config,
        },
        "results": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "passRate": pass_rate,
            "cases": [
                {"name": r.case_name, "passed": r.passed, "score": r.score}
                for r in run.results
            ],
        },
        "limitations": (
            "Evidence covers only the test cases listed above and the configured "
            "graders; it is testing evidence, not a conformity certification."
        ),
    }
    digest = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    return {**body, "contentHash": f"sha256:{digest}"}


def render_markdown(evidence: dict[str, Any]) -> str:
    """Render a testing-evidence document as human-readable Markdown."""
    subj = evidence.get("subject", {})
    res = evidence.get("results", {})
    meth = evidence.get("testingMethodology", {})
    rate = res.get("passRate")
    rate_str = f"{rate:.1%}" if isinstance(rate, (int, float)) else "n/a"
    lines = [
        "# EU AI Act — Testing Evidence",
        "",
        f"**Standard:** {evidence.get('standard')}  ",
        f"**Agent:** `{subj.get('agentId')}`  ",
        f"**Suite:** {subj.get('suite')}  ",
        f"**Run:** `{evidence.get('run', {}).get('id')}` ({evidence.get('run', {}).get('createdAt')})  ",
        f"**Content hash:** `{evidence.get('contentHash')}`",
        "",
        "## Results",
        "",
        f"- Total cases: {res.get('total')}",
        f"- Passed: {res.get('passed')}",
        f"- Failed: {res.get('failed')}",
        f"- Pass rate: {rate_str}",
        f"- Graders: {', '.join(meth.get('graders', [])) or 'n/a'}",
        "",
        "## Cases",
        "",
        "| Case | Result | Score |",
        "|------|--------|-------|",
    ]
    for c in res.get("cases", []):
        lines.append(f"| {c.get('name')} | {'PASS' if c.get('passed') else 'FAIL'} | {c.get('score')} |")
    lines += ["", f"> {evidence.get('limitations')}"]
    return "\n".join(lines)
