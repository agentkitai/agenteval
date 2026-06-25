"""Tests for the AgentLens emitter (the emit-TO-AgentLens federation direction)."""

from __future__ import annotations

import httpx
import pytest

from agenteval.emitters import agentlens as emitter
from agenteval.emitters.agentlens import (
    AgentLensEmitError,
    emit_eval_run,
    method_for_graders,
    run_to_payload,
)
from agenteval.models import EvalResult, EvalRun


def _result(name: str, passed: bool, score: float, reason: str | None = None) -> EvalResult:
    return EvalResult(
        case_name=name,
        passed=passed,
        score=score,
        details={"reason": reason} if reason else {},
        agent_output="",
        tools_called=[],
        tokens_in=0,
        tokens_out=0,
        cost_usd=None,
        latency_ms=0,
    )


def _run(results, *, agent_ref="mod:agent", cost=0.05) -> EvalRun:
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    return EvalRun(
        id="run_abc123",
        suite="pii-suite",
        agent_ref=agent_ref,
        config={},
        results=results,
        summary={
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / len(results)) if results else 0.0,
            "total_cost_usd": cost,
            "avg_latency_ms": 0.0,
        },
        created_at="2026-06-25T12:00:00.000Z",
    )


def test_payload_maps_summary_and_failed_cases():
    run = _run([
        _result("ok", True, 1.0),
        _result("leaks-ssn", False, 0.0, reason="SSN present"),
        _result("leaks-email", False, 0.2),  # no reason → no detail key
    ])
    p = run_to_payload(run, session_id="eval-run_abc123", tenant_id="default", method="deterministic")

    assert p["tenantId"] == "default"
    assert p["sessionId"] == "eval-run_abc123"
    assert p["agentId"] == "mod:agent"
    assert p["run"]["id"] == "run_abc123"
    assert p["run"]["suite"] == "pii-suite"
    assert p["run"]["method"] == "deterministic"
    assert p["run"]["summary"] == {
        "total": 3, "passed": 1, "failed": 2, "passRate": 1 / 3, "totalCostUsd": 0.05,
    }
    failed = p["run"]["failedCases"]
    assert [c["name"] for c in failed] == ["leaks-ssn", "leaks-email"]
    assert failed[0]["detail"] == "SSN present"
    # No reason supplied → 'detail' is omitted (server synthesizes from score).
    assert "detail" not in failed[1]


def test_payload_omits_zero_cost_and_handles_empty_agent_ref():
    run = _run([_result("ok", True, 1.0)], agent_ref="", cost=0.0)
    p = run_to_payload(run, session_id="s", tenant_id="t", method="deterministic")
    # totalCostUsd must be ABSENT (not null) when there's no cost — zod optional rejects null.
    assert "totalCostUsd" not in p["run"]["summary"]
    # Empty agent_ref falls back to a non-empty placeholder (server requires min(1)).
    assert p["agentId"] == "unknown"


def test_failed_cases_capped_at_1000():
    run = _run([_result(f"c{i}", False, 0.0) for i in range(1500)])
    p = run_to_payload(run, session_id="s", tenant_id="t", method="deterministic")
    assert len(p["run"]["failedCases"]) == 1000
    # The authoritative count is still the true total, not the truncated detail.
    assert p["run"]["summary"]["failed"] == 1500


def test_method_for_graders():
    assert method_for_graders(["exact_match", "contains"]) == "deterministic"
    assert method_for_graders(["exact_match", "llm_judge"]) == "llm_judge"
    assert method_for_graders(["semantic_similarity"]) == "llm_judge"
    assert method_for_graders([]) == "deterministic"


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 201

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    """Stand-in for httpx.Client capturing the POST and returning a canned response."""

    captured = {}

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json, headers, timeout):
        _FakeClient.captured = {"url": url, "json": json, "headers": headers}
        return _FakeResp({"recorded": True, "sessionId": json["sessionId"]})


def test_emit_success_builds_url_auth_and_synthetic_session(monkeypatch):
    monkeypatch.setattr(emitter.httpx, "Client", _FakeClient)
    run = _run([_result("ok", True, 1.0)])
    resp = emit_eval_run(run, server_url="https://lens.example/", token="svc-tok", grader_names=["exact_match"])

    assert resp["recorded"] is True
    cap = _FakeClient.captured
    assert cap["url"] == "https://lens.example/api/internal/eval/run"
    assert cap["headers"]["Authorization"] == "Bearer svc-tok"
    # No explicit session_id → synthetic per-run id.
    assert cap["json"]["sessionId"] == "eval-run_abc123"
    # tenantId reaches the wire (defaults to 'default') — guards tenant routing.
    assert cap["json"]["tenantId"] == "default"
    # Method derived from graders.
    assert cap["json"]["run"]["method"] == "deterministic"


def test_emit_uses_explicit_session_id(monkeypatch):
    monkeypatch.setattr(emitter.httpx, "Client", _FakeClient)
    run = _run([_result("ok", True, 1.0)])
    emit_eval_run(run, server_url="https://lens.example", token="t", session_id="real-session-7")
    assert _FakeClient.captured["json"]["sessionId"] == "real-session-7"


def test_emit_uses_explicit_tenant_id(monkeypatch):
    monkeypatch.setattr(emitter.httpx, "Client", _FakeClient)
    run = _run([_result("ok", True, 1.0)])
    emit_eval_run(run, server_url="https://lens.example", token="t", tenant_id="acme-corp")
    assert _FakeClient.captured["json"]["tenantId"] == "acme-corp"


def test_emit_fail_soft_on_transport_error(monkeypatch):
    class _BoomClient(_FakeClient):
        def post(self, *a, **k):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(emitter.httpx, "Client", _BoomClient)
    run = _run([_result("ok", True, 1.0)])
    with pytest.raises(AgentLensEmitError):
        emit_eval_run(run, server_url="https://lens.example", token="t")


def test_emit_fail_soft_on_http_error(monkeypatch):
    class _RejectClient(_FakeClient):
        def post(self, url, json, headers, timeout):
            req = httpx.Request("POST", url)
            resp = httpx.Response(401, request=req)
            raise httpx.HTTPStatusError("unauthorized", request=req, response=resp)

    monkeypatch.setattr(emitter.httpx, "Client", _RejectClient)
    run = _run([_result("ok", True, 1.0)])
    with pytest.raises(AgentLensEmitError, match="HTTP 401"):
        emit_eval_run(run, server_url="https://lens.example", token="bad")


def test_emit_fail_soft_on_unparseable_body(monkeypatch):
    """A 2xx with a non-JSON body must not escape as a raw ValueError."""
    class _BadJsonResp(_FakeResp):
        def json(self):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    class _BadJsonClient(_FakeClient):
        def post(self, url, json, headers, timeout):
            return _BadJsonResp({})

    monkeypatch.setattr(emitter.httpx, "Client", _BadJsonClient)
    run = _run([_result("ok", True, 1.0)])
    with pytest.raises(AgentLensEmitError, match="unparseable"):
        emit_eval_run(run, server_url="https://lens.example", token="t")
