"""Independent eval-evidence verify (#10)."""

import httpx
import pytest

from agenteval import verify as V


class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


def test_session_id_for_run():
    assert V.session_id_for_run("abc123") == "eval-abc123"


def test_verified_chain_with_session(monkeypatch):
    monkeypatch.setattr(V.httpx, "get", lambda *a, **k: _Resp(payload={
        "verified": True, "sessionsVerified": 1, "firstHash": "h0", "lastHash": "h1", "brokenChains": [],
    }))
    r = V.verify_eval_evidence(server="https://lens", api_key="k", session_id="eval-x")
    assert r["verified"] is True
    assert r["chainVerified"] is True and r["sessionsVerified"] == 1
    assert r["lastHash"] == "h1"


def test_absent_session_is_unverified_not_vacuous(monkeypatch):
    # Chain "verifies" with no sessions → must be reported unverified (nothing to attest).
    monkeypatch.setattr(V.httpx, "get", lambda *a, **k: _Resp(payload={"verified": True, "sessionsVerified": 0}))
    r = V.verify_eval_evidence(server="https://lens", api_key="k", session_id="eval-missing")
    assert r["verified"] is False
    assert r["chainVerified"] is True


def test_broken_chain_is_unverified(monkeypatch):
    monkeypatch.setattr(V.httpx, "get", lambda *a, **k: _Resp(payload={
        "verified": False, "sessionsVerified": 1, "brokenChains": [{"sessionId": "eval-x"}],
    }))
    r = V.verify_eval_evidence(server="https://lens", api_key="k", session_id="eval-x")
    assert r["verified"] is False
    assert r["brokenChains"]


def test_non_200_raises_verifyerror(monkeypatch):
    monkeypatch.setattr(V.httpx, "get", lambda *a, **k: _Resp(status_code=403, text="Forbidden"))
    with pytest.raises(V.VerifyError):
        V.verify_eval_evidence(server="https://lens", api_key="bad", session_id="eval-x")


def test_transport_error_raises_verifyerror(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(V.httpx, "get", boom)
    with pytest.raises(V.VerifyError):
        V.verify_eval_evidence(server="https://lens", api_key="k", session_id="eval-x")


def test_command_registered():
    from click.testing import CliRunner

    from agenteval.cli import cli

    res = CliRunner().invoke(cli, ["verify-evidence", "--help"])
    assert res.exit_code == 0
    assert "verify a run's eval evidence" in res.output.lower()
