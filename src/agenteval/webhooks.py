"""Webhook notifications for AgentEval.

Supports generic JSON webhooks, Slack Block Kit, and Discord embeds.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from agenteval.models import EvalRun


@dataclass
class WebhookConfig:
    """Configuration for webhook notifications."""
    url: str
    format: str = "generic"  # generic, slack, discord
    on_failure_only: bool = False
    timeout: float = 10.0
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class WebhookResult:
    """Result of a webhook notification."""
    success: bool
    status_code: Optional[int] = None
    error: Optional[str] = None


def detect_webhook_format(url: str) -> str:
    """Auto-detect webhook format from URL pattern."""
    if "hooks.slack.com" in url:
        return "slack"
    if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
        return "discord"
    return "generic"


def format_generic_payload(run: EvalRun) -> Dict[str, Any]:
    """Format a generic JSON payload for webhook."""
    s = run.summary
    return {
        "event": "eval_complete",
        "suite": run.suite,
        "run_id": run.id,
        "passed": s.get("failed", 0) == 0,
        "total": s.get("total", 0),
        "passed_count": s.get("passed", 0),
        "failed_count": s.get("failed", 0),
        "pass_rate": s.get("pass_rate", 0.0),
        "total_cost_usd": s.get("total_cost_usd", 0.0),
        "avg_latency_ms": s.get("avg_latency_ms", 0.0),
        "created_at": run.created_at,
        "regressions": [],
        "failed_cases": [r.case_name for r in run.results if not r.passed],
    }


def format_slack_payload(run: EvalRun) -> Dict[str, Any]:
    """Format a Slack Block Kit payload."""
    s = run.summary
    passed = s.get("failed", 0) == 0
    emoji = "✅" if passed else "❌"
    status = "PASSED" if passed else "FAILED"
    color = "#36a64f" if passed else "#e01e5a"

    failed_cases = [r.case_name for r in run.results if not r.passed]
    failed_text = "\n".join(f"• {c}" for c in failed_cases[:10]) if failed_cases else "None"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} AgentEval: {status}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Suite:* {run.suite}"},
                {"type": "mrkdwn", "text": f"*Run:* {run.id}"},
                {"type": "mrkdwn", "text": f"*Pass Rate:* {s.get('pass_rate', 0):.0%}"},
                {"type": "mrkdwn", "text": f"*Total:* {s.get('total', 0)} cases"},
            ],
        },
    ]

    if failed_cases:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Failed Cases:*\n{failed_text}"},
        })

    if s.get("total_cost_usd"):
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Cost: ${s['total_cost_usd']:.4f} | Latency: {s.get('avg_latency_ms', 0):.0f}ms"},
            ],
        })

    return {
        "blocks": blocks,
        "attachments": [{"color": color, "blocks": []}],
    }


def format_discord_payload(run: EvalRun) -> Dict[str, Any]:
    """Format a Discord embed payload."""
    s = run.summary
    passed = s.get("failed", 0) == 0
    color = 0x36A64F if passed else 0xE01E5A
    status = "✅ PASSED" if passed else "❌ FAILED"

    failed_cases = [r.case_name for r in run.results if not r.passed]
    failed_text = "\n".join(f"• {c}" for c in failed_cases[:10]) if failed_cases else "None"

    fields = [
        {"name": "Suite", "value": run.suite, "inline": True},
        {"name": "Pass Rate", "value": f"{s.get('pass_rate', 0):.0%}", "inline": True},
        {"name": "Total", "value": str(s.get("total", 0)), "inline": True},
        {"name": "Passed", "value": str(s.get("passed", 0)), "inline": True},
        {"name": "Failed", "value": str(s.get("failed", 0)), "inline": True},
    ]

    if s.get("total_cost_usd"):
        fields.append({"name": "Cost", "value": f"${s['total_cost_usd']:.4f}", "inline": True})

    if failed_cases:
        fields.append({"name": "Failed Cases", "value": failed_text, "inline": False})

    return {
        "embeds": [{
            "title": f"AgentEval: {status}",
            "color": color,
            "fields": fields,
            "footer": {"text": f"Run {run.id} | {run.created_at[:19]}"},
        }],
    }


_FORMATTERS = {
    "generic": format_generic_payload,
    "slack": format_slack_payload,
    "discord": format_discord_payload,
}


def send_webhook(
    run: EvalRun,
    config: WebhookConfig,
) -> WebhookResult:
    """Send a webhook notification for an eval run.

    Args:
        run: The eval run.
        config: Webhook configuration.

    Returns:
        WebhookResult with success status.
    """
    # Check failure-only filter
    if config.on_failure_only and run.summary.get("failed", 0) == 0:
        return WebhookResult(success=True, status_code=None, error="Skipped (no failures)")

    # Auto-detect format if generic
    fmt = config.format
    if fmt == "generic":
        detected = detect_webhook_format(config.url)
        if detected != "generic":
            fmt = detected

    formatter = _FORMATTERS.get(fmt, format_generic_payload)
    payload = formatter(run)

    headers = {"Content-Type": "application/json", **config.headers}

    try:
        resp = httpx.post(
            config.url,
            json=payload,
            headers=headers,
            timeout=config.timeout,
        )
        success = 200 <= resp.status_code < 300
        return WebhookResult(
            success=success,
            status_code=resp.status_code,
            error=None if success else f"HTTP {resp.status_code}",
        )
    except httpx.TimeoutException:
        return WebhookResult(success=False, error="Timeout")
    except Exception as e:
        return WebhookResult(success=False, error=str(e))
