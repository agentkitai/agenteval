"""Independently verify federated eval evidence in AgentLens (#10).

The agenteval->AgentLens federation records each run as a server-authoritative,
hash-chained ``eval_result`` under session ``eval-<run id>``. That event type is
excluded from AgentLens's client ingest enum, so a client CANNOT forge one — a
verified eval session is therefore genuine eval evidence. This module asks
AgentLens to re-walk the session's hash chain (``GET /api/audit/verify``) and
confirms it is intact and non-empty. You can verify; you can't forge.
"""

from __future__ import annotations

from typing import Any, Dict

import httpx


class VerifyError(Exception):
    """Raised when the verification request to AgentLens cannot be completed."""


def session_id_for_run(run_id: str) -> str:
    """The synthetic AgentLens session id the federation uses for a run."""
    return f"eval-{run_id}"


def verify_eval_evidence(
    *,
    server: str,
    api_key: str,
    session_id: str,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Verify one session's eval-evidence chain via AgentLens.

    Calls ``GET /api/audit/verify?sessionId=...`` (needs an AgentLens API key with
    an audit/admin role). Returns a dict with ``verified`` (the chain is intact
    AND the session exists — ``sessionsVerified >= 1``, so an absent session that
    verifies *vacuously* is reported unverified), plus the underlying chain
    fields. Raises :class:`VerifyError` on a transport/HTTP failure.
    """
    url = server.rstrip("/") + "/api/audit/verify"
    try:
        resp = httpx.get(
            url,
            params={"sessionId": session_id},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise VerifyError(f"request to AgentLens failed: {e}") from e
    if resp.status_code != 200:
        raise VerifyError(f"AgentLens returned HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError as e:
        raise VerifyError(f"AgentLens response was not JSON: {e}") from e

    chain_verified = bool(data.get("verified"))
    sessions = int(data.get("sessionsVerified") or 0)
    return {
        "sessionId": session_id,
        # A session that doesn't exist verifies vacuously — require >= 1 so
        # "verify a run that was never federated" is reported as unverified.
        "verified": chain_verified and sessions >= 1,
        "chainVerified": chain_verified,
        "sessionsVerified": sessions,
        "firstHash": data.get("firstHash"),
        "lastHash": data.get("lastHash"),
        "brokenChains": data.get("brokenChains") or [],
    }
