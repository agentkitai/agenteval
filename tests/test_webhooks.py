"""Tests for webhook notifications."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agenteval.models import EvalResult, EvalRun
from agenteval.webhooks import (
    WebhookConfig,
    detect_webhook_format,
    format_discord_payload,
    format_generic_payload,
    format_slack_payload,
    send_webhook,
)


def _make_run(failed=0):
    results = []
    for i in range(3):
        passed = i >= failed
        results.append(EvalResult(
            case_name=f"case{i+1}", passed=passed,
            score=1.0 if passed else 0.0, details={"reason": "test"},
            agent_output="ok", tools_called=[], tokens_in=100,
            tokens_out=50, cost_usd=0.01, latency_ms=100,
        ))
    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    return EvalRun(
        id="run1", suite="test-suite", agent_ref="test:agent", config={},
        results=results,
        summary={
            "total": total, "passed": passed_count,
            "failed": total - passed_count,
            "pass_rate": passed_count / total,
            "total_cost_usd": 0.03, "avg_latency_ms": 100,
        },
        created_at="2026-01-01T00:00:00Z",
    )


class TestDetectFormat:
    def test_slack(self):
        assert detect_webhook_format("https://hooks.slack.com/services/T/B/X") == "slack"

    def test_discord(self):
        assert detect_webhook_format("https://discord.com/api/webhooks/123/abc") == "discord"

    def test_generic(self):
        assert detect_webhook_format("https://example.com/hook") == "generic"


class TestFormatGeneric:
    def test_all_pass(self):
        run = _make_run(failed=0)
        payload = format_generic_payload(run)
        assert payload["passed"] is True
        assert payload["suite"] == "test-suite"
        assert payload["total"] == 3
        assert payload["failed_cases"] == []

    def test_with_failures(self):
        run = _make_run(failed=2)
        payload = format_generic_payload(run)
        assert payload["passed"] is False
        assert len(payload["failed_cases"]) == 2


class TestFormatSlack:
    def test_structure(self):
        run = _make_run(failed=1)
        payload = format_slack_payload(run)
        assert "blocks" in payload
        assert len(payload["blocks"]) >= 2

    def test_passing_run(self):
        run = _make_run(failed=0)
        payload = format_slack_payload(run)
        header = payload["blocks"][0]
        assert "PASSED" in header["text"]["text"]


class TestFormatDiscord:
    def test_structure(self):
        run = _make_run(failed=1)
        payload = format_discord_payload(run)
        assert "embeds" in payload
        embed = payload["embeds"][0]
        assert "FAILED" in embed["title"]
        assert embed["color"] == 0xE01E5A

    def test_passing_run(self):
        run = _make_run(failed=0)
        payload = format_discord_payload(run)
        embed = payload["embeds"][0]
        assert "PASSED" in embed["title"]
        assert embed["color"] == 0x36A64F


class TestSendWebhook:
    @patch("agenteval.webhooks.httpx.post")
    def test_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        run = _make_run()
        config = WebhookConfig(url="https://example.com/hook")
        result = send_webhook(run, config)
        assert result.success is True
        assert result.status_code == 200

    @patch("agenteval.webhooks.httpx.post")
    def test_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        run = _make_run()
        config = WebhookConfig(url="https://example.com/hook")
        result = send_webhook(run, config)
        assert result.success is False

    def test_failure_only_skips_passing(self):
        run = _make_run(failed=0)
        config = WebhookConfig(url="https://example.com/hook", on_failure_only=True)
        result = send_webhook(run, config)
        assert result.success is True
        assert "Skipped" in (result.error or "")

    @patch("agenteval.webhooks.httpx.post")
    def test_failure_only_sends_on_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        run = _make_run(failed=1)
        config = WebhookConfig(url="https://example.com/hook", on_failure_only=True)
        result = send_webhook(run, config)
        assert result.success is True
        mock_post.assert_called_once()

    @patch("agenteval.webhooks.httpx.post")
    def test_auto_detect_slack(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        run = _make_run()
        config = WebhookConfig(url="https://hooks.slack.com/services/T/B/X")
        send_webhook(run, config)
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "blocks" in payload  # Slack format

    @patch("agenteval.webhooks.httpx.post", side_effect=Exception("connection error"))
    def test_exception_handling(self, mock_post):
        run = _make_run()
        config = WebhookConfig(url="https://example.com/hook")
        result = send_webhook(run, config)
        assert result.success is False
        assert "connection error" in result.error
