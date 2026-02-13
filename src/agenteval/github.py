"""GitHub API client for posting PR comments via urllib."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Optional


class GitHubClient:
    """Post and update PR comments via the GitHub REST API."""

    API_BASE = "https://api.github.com"

    def __init__(self, token: str, repo: str, pr_number: int) -> None:
        self.token = token
        self.repo = repo
        self.pr_number = pr_number

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        url = f"{self.API_BASE}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"token {self.token}")
        req.add_header("Accept", "application/vnd.github.v3+json")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                raise ValueError(f"GitHub API {e.code}: {e.reason}") from e
            raise RuntimeError(f"GitHub API {e.code}: {e.reason}") from e

    def post_comment(self, body: str) -> dict:
        """POST a new comment on the PR."""
        return self._request(
            "POST",
            f"/repos/{self.repo}/issues/{self.pr_number}/comments",
            {"body": body},
        )

    def update_comment(self, comment_id: int, body: str) -> dict:
        """PATCH an existing comment."""
        return self._request(
            "PATCH",
            f"/repos/{self.repo}/issues/comments/{comment_id}",
            {"body": body},
        )

    def find_comment(self, marker: str) -> Optional[int]:
        """Find a comment containing the marker string. Returns comment ID or None.

        Paginates through all comments (up to 10 pages).
        """
        page = 1
        while page <= 10:
            comments = self._request(
                "GET",
                f"/repos/{self.repo}/issues/{self.pr_number}/comments?per_page=100&page={page}",
            )
            for c in comments:
                if marker in c.get("body", ""):
                    return c["id"]
            if len(comments) < 100:
                break
            page += 1
        return None

    def post_or_update_comment(
        self, body: str, marker: str = "<!-- agenteval-results -->"
    ) -> dict:
        """Post a new comment or update existing one containing the marker."""
        existing = self.find_comment(marker)
        if existing is not None:
            return self.update_comment(existing, body)
        return self.post_comment(body)
