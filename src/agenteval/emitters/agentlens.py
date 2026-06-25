"""Emit a completed EvalRun to AgentLens as tamper-evident eval evidence.

The reverse of ``importers/agentlens`` (which imports sessions FROM AgentLens):
here an :class:`~agenteval.models.EvalRun` is POSTed to AgentLens's internal
federation endpoint ``POST /api/internal/eval/run``, which records it as a
hash-chained, server-authoritative ``eval_result`` in a session's audit trail.

agenteval holds no AgentLens session, so by default we pass a synthetic per-run
session id (``eval-<run id>``) and the server genesis-chains the result; pass an
explicit ``session_id`` to chain into an existing instrumented-agent session.

The endpoint is gated by the shared AgentGate service token (it is service-token
authed, not API-key authed). Emission is best-effort: a failure here must never
fail the eval run, so callers catch :class:`AgentLensEmitError` and warn.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

import httpx

from agenteval.models import EvalRun

# AgentLens caps failedCases at 1000; sending more would 400 and lose ALL the
# evidence. Truncate the per-case detail (the summary counts stay accurate).
_MAX_FAILED_CASES = 1000

# Graders whose verdict isn't reproducible: if any case used one, the run is an
# LLM/semantic judgment, not deterministic evidence. Substring match on the
# grader name keeps it robust to 'llm_judge', 'semantic_similarity', 'llm:gpt-4o'.
_NONDETERMINISTIC_GRADER_TOKENS = ("llm", "semantic")


class AgentLensEmitError(Exception):
    """Raised when emitting an EvalRun to AgentLens fails."""


def method_for_graders(grader_names: List[str]) -> str:
    """Classify a run's evidence as 'deterministic' or 'llm_judge' from its graders.

    ponytail: substring heuristic on grader names. If a custom *deterministic*
    grader is ever named with 'llm'/'semantic', pass ``method=`` to
    :func:`emit_eval_run` explicitly to override.
    """
    for name in grader_names:
        lowered = name.lower()
        if any(tok in lowered for tok in _NONDETERMINISTIC_GRADER_TOKENS):
            return "llm_judge"
    return "deterministic"


def run_to_payload(
    run: EvalRun,
    *,
    session_id: str,
    tenant_id: str,
    method: str,
) -> Dict[str, Any]:
    """Map an :class:`EvalRun` to the AgentLens federation request body.

    Pure (no I/O) so the mapping is unit-testable. Omits optional fields rather
    than sending ``null`` — AgentLens validates with ``z.number().optional()``,
    which rejects ``null`` but accepts an absent key.
    """
    s = run.summary
    summary: Dict[str, Any] = {
        "total": int(s.get("total", 0)),
        "passed": int(s.get("passed", 0)),
        "failed": int(s.get("failed", 0)),
        "passRate": float(s.get("pass_rate", 0.0)),
    }
    cost = s.get("total_cost_usd")
    if cost:
        summary["totalCostUsd"] = float(cost)

    failed_cases: List[Dict[str, Any]] = []
    for r in run.results:
        if r.passed:
            continue
        case: Dict[str, Any] = {"name": r.case_name, "score": float(r.score)}
        reason = r.details.get("reason") if isinstance(r.details, dict) else None
        if reason:
            case["detail"] = str(reason)[:1000]
        failed_cases.append(case)
    failed_cases = failed_cases[:_MAX_FAILED_CASES]

    return {
        "tenantId": tenant_id,
        "sessionId": session_id,
        # AgentLens requires a non-empty agentId; batch-import suites carry "".
        "agentId": run.agent_ref or "unknown",
        "run": {
            "id": run.id,
            "suite": run.suite,
            "createdAt": run.created_at,
            "method": method,
            "summary": summary,
            "failedCases": failed_cases,
        },
    }


def emit_eval_run(
    run: EvalRun,
    *,
    server_url: str,
    token: Optional[str],
    session_id: Optional[str] = None,
    tenant_id: str = "default",
    method: Optional[str] = None,
    grader_names: Optional[List[str]] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """POST an EvalRun to AgentLens's federation endpoint.

    Returns the parsed JSON response on success. Raises :class:`AgentLensEmitError`
    on any HTTP or transport failure — the caller decides whether to warn-and-continue.
    """
    sid = session_id or f"eval-{run.id}"
    resolved_method = method or method_for_graders(grader_names or [])
    payload = run_to_payload(run, session_id=sid, tenant_id=tenant_id, method=resolved_method)

    url = f"{server_url.rstrip('/')}/api/internal/eval/run"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client() as http:
            resp = http.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return cast(Dict[str, Any], resp.json())
    except httpx.HTTPStatusError as e:
        raise AgentLensEmitError(
            f"AgentLens rejected the eval run: HTTP {e.response.status_code}"
        ) from e
    except httpx.RequestError as e:
        raise AgentLensEmitError(f"Request to AgentLens failed: {e}") from e
    except ValueError as e:
        # A 2xx with an unparseable body — json.JSONDecodeError subclasses ValueError.
        # Stay best-effort: surface it as our own error so the caller warns, not crashes.
        raise AgentLensEmitError(f"AgentLens returned an unparseable response: {e}") from e
