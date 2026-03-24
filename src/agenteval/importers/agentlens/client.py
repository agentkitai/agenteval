"""AgentLens HTTP client and batch-import helper."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from agenteval.importers.agentlens.mapper import AgentLensImportError, import_session
from agenteval.models import EvalCase, EvalSuite


class AgentLensClient:
    """HTTP client for the AgentLens server API."""

    def __init__(self, server_url: str, api_key: Optional[str] = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get(self, url: str, **kwargs: Any) -> Any:
        """Perform a GET request, creating a client if needed."""
        try:
            with httpx.Client() as http:
                resp = http.get(url, headers=self._headers(), **kwargs)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise AgentLensImportError(
                f"Failed to fetch {url}: HTTP {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise AgentLensImportError(f"Request failed: {e}") from e

    def fetch_session(self, session_id: str) -> dict:
        """Fetch a single session by ID from the AgentLens server."""
        return self._get(f"{self.server_url}/sessions/{session_id}")

    def list_sessions(
        self, filter_tags: Optional[List[str]] = None, limit: int = 50
    ) -> List[dict]:
        """List sessions from the AgentLens server."""
        params: Dict[str, Any] = {"limit": limit}
        if filter_tags:
            params["tags"] = ",".join(filter_tags)
        return self._get(f"{self.server_url}/sessions", params=params)


def batch_import(
    client: AgentLensClient,
    filter_tags: Optional[List[str]] = None,
    limit: int = 50,
) -> EvalSuite:
    """Import multiple sessions from AgentLens server as an EvalSuite.

    Calls list_sessions with filter, fetches each, combines into a suite.
    """
    session_summaries = client.list_sessions(filter_tags=filter_tags, limit=limit)
    cases: List[EvalCase] = []
    for summary in session_summaries:
        session_id = summary.get("id", "")
        session_data = client.fetch_session(session_id)
        case = import_session(session_data)
        if case is not None:
            cases.append(case)

    return EvalSuite(name="agentlens-batch-import", agent="", cases=cases)
