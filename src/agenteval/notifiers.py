"""Unified notifier interface for AgentEval.

Provides a simple ``Notifier`` protocol and concrete wrappers around
existing webhook and GitHub notification mechanisms.  The CLI commands
are **not** changed — these classes are a foundation for future use.
"""

from __future__ import annotations

from typing import Any, Protocol


class Notifier(Protocol):
    """Protocol that all notifier implementations must satisfy."""

    def send(self, payload: dict) -> Any:
        """Send a notification payload.  Returns implementation-specific result."""
        ...


# ── Concrete wrappers ────────────────────────────────────────────────────


class WebhookNotifier:
    """Sends eval-run results via a generic/Slack/Discord webhook.

    Wraps :func:`agenteval.webhooks.send_webhook`.
    """

    def __init__(self, config: agenteval.webhooks.WebhookConfig) -> None:  # noqa: F821
        from agenteval.webhooks import (
            WebhookConfig,  # deferred to avoid hard dep at import time
        )

        self._config: WebhookConfig = config

    def send(self, payload: dict) -> Any:
        """Send *payload* as an :class:`~agenteval.models.EvalRun`.

        ``payload`` must contain an ``"eval_run"`` key whose value is an
        :class:`~agenteval.models.EvalRun` instance.

        Returns a :class:`~agenteval.webhooks.WebhookResult`.
        """
        from agenteval.webhooks import send_webhook

        eval_run = payload["eval_run"]
        return send_webhook(eval_run, self._config)


class GitHubNotifier:
    """Posts or updates a GitHub PR comment with notification content.

    Wraps :meth:`agenteval.github.GitHubClient.post_comment`.
    """

    def __init__(self, token: str, repo: str, pr_number: int) -> None:
        from agenteval.github import GitHubClient

        self._client = GitHubClient(token, repo, pr_number)

    def send(self, payload: dict) -> Any:
        """Post a comment to the configured PR.

        ``payload`` must contain a ``"body"`` key with the comment
        markdown string.

        Returns the GitHub API response dict.
        """
        body = payload["body"]
        return self._client.post_comment(body)
