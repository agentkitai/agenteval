"""The 'ci', 'github-comment', 'webhook', and 'badge' commands."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional

import click

from agenteval.loader import LoadError, load_suite
from agenteval.runner import run_suite
from agenteval.store import ResultStore


def register(cli: click.Group, helpers: dict) -> None:
    """Register CI-related commands on the CLI group."""

    @cli.command("ci")
    @click.argument("suite_path", type=click.Path(exists=True))
    @click.option("--agent", required=True, help="Agent callable as 'module:func'.")
    @click.option("--min-pass-rate", default=0.8, show_default=True, type=float, help="Minimum pass rate (0-1).")
    @click.option("--max-regression", default=10.0, show_default=True, type=float, help="Max regression percentage.")
    @click.option("--baseline", default=None, help="Baseline run ID for regression detection.")
    @click.option("--format", "fmt", default="text", type=click.Choice(["text", "json", "junit"]), show_default=True,
                  help="Output format.")
    @click.option("--output", "-o", default=None, type=click.Path(), help="Write output to file.")
    @click.option("--parallel", default=1, show_default=True, type=int, help="Max concurrent cases.")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    def ci_cmd(suite_path: str, agent: str, min_pass_rate: float, max_regression: float,
               baseline: Optional[str], fmt: str, output: Optional[str], parallel: int, db: str) -> None:
        """Run a suite and check CI thresholds. Exit 0 if passed, 1 if failed."""
        import agenteval.cli as _cli_mod
        _fail = _cli_mod._fail
        _resolve_callable = _cli_mod._resolve_callable

        if not 0.0 <= min_pass_rate <= 1.0:
            _fail("--min-pass-rate must be between 0.0 and 1.0.")
        if max_regression < 0.0 or max_regression > 100.0:
            _fail("--max-regression must be between 0 and 100.")
        from agenteval.ci import CIConfig, check_thresholds

        try:
            eval_suite = load_suite(suite_path)
        except LoadError as e:
            _fail(f"Loading suite: {e}")

        try:
            agent_fn = _resolve_callable(agent)
        except click.BadParameter as e:
            _fail(e.format_message())

        store = ResultStore(db)
        try:
            eval_run = asyncio.run(
                run_suite(eval_suite, agent_fn, store=store, parallel=parallel)
            )

            baseline_run = None
            if baseline:
                baseline_run = store.get_run(baseline)
                if baseline_run is None:
                    _fail(f"Baseline run '{baseline}' not found.")
        finally:
            store.close()

        config = CIConfig(min_pass_rate=min_pass_rate, max_regression_pct=max_regression)
        ci_result = check_thresholds(eval_run, config, baseline=baseline_run)

        # Format output
        if fmt == "json":
            from agenteval.formatters.json_fmt import format_json
            text = format_json(ci_result, eval_run)
        elif fmt == "junit":
            from agenteval.formatters.junit import format_junit
            text = format_junit(ci_result, eval_run)
        else:
            text = ci_result.summary

        if output:
            with open(output, "w") as f:
                f.write(text)
        else:
            click.echo(text)

        sys.exit(0 if ci_result.passed else 1)

    @cli.command("github-comment")
    @click.option("--run", "run_id", required=True, help="Run ID to comment on.")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    @click.option("--dry-run", "dry_run", is_flag=True, help="Print comment without posting.")
    def github_comment_cmd(run_id: str, db: str, dry_run: bool) -> None:
        """Post or update a GitHub PR comment with eval results."""
        import agenteval.cli as _cli_mod
        _fail = _cli_mod._fail

        from agenteval.ci import CIConfig, check_thresholds
        from agenteval.formatters.github_comment import format_github_comment
        store = ResultStore(db)
        try:
            eval_run = store.get_run(run_id)
            if eval_run is None:
                _fail(f"Run '{run_id}' not found.")
        finally:
            store.close()

        ci_result = check_thresholds(eval_run, CIConfig())
        comment = format_github_comment(ci_result, eval_run)

        if dry_run:
            click.echo(comment)
            return

        token = os.environ.get("GITHUB_TOKEN")
        repo = os.environ.get("GITHUB_REPOSITORY")
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not all([token, repo, event_path]):
            _fail("GITHUB_TOKEN, GITHUB_REPOSITORY, and GITHUB_EVENT_PATH must be set.")

        import json as _json
        with open(event_path) as f:
            event = _json.load(f)
        pr_number = event.get("pull_request", {}).get("number") or event.get("number")
        if not pr_number:
            _fail("Could not determine PR number from GITHUB_EVENT_PATH.")

        from agenteval.github import GitHubClient
        client = GitHubClient(token, repo, int(pr_number))
        client.post_or_update_comment(comment)
        click.echo(f"Comment posted to {repo}#{pr_number}")

    @cli.command("webhook")
    @click.option("--run", "run_id", required=True, help="Run ID.")
    @click.option("--url", required=True, help="Webhook URL.")
    @click.option("--format", "fmt", default="generic", type=click.Choice(["generic", "slack", "discord"]),
                  show_default=True, help="Payload format.")
    @click.option("--failure-only", is_flag=True, help="Only send on failure.")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    def webhook_cmd(run_id: str, url: str, fmt: str, failure_only: bool, db: str) -> None:
        """Send a webhook notification for an eval run."""
        from agenteval.webhooks import WebhookConfig, send_webhook

        store = ResultStore(db)
        try:
            eval_run = store.get_run(run_id)
        finally:
            store.close()

        if eval_run is None:
            click.echo(f"Error: Run '{run_id}' not found.", err=True)
            sys.exit(1)

        config = WebhookConfig(url=url, format=fmt, on_failure_only=failure_only)
        result = send_webhook(eval_run, config)
        if result.success:
            click.echo(f"Webhook sent successfully (status={result.status_code})")
        else:
            click.echo(f"Webhook failed: {result.error}", err=True)
            sys.exit(1)

    @cli.command("badge")
    @click.option("--run", "run_id", required=True, help="Run ID.")
    @click.option("--output", "-o", required=True, type=click.Path(), help="Output SVG path.")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    def badge_cmd(run_id: str, output: str, db: str) -> None:
        """Generate a pass-rate badge SVG.

        Examples:

          agenteval badge --run abc123 --output badge.svg

          agenteval badge --run abc123 --output badge.svg --db results.db
        """
        from agenteval.badge import generate_badge
        from agenteval.ci import CIConfig, check_thresholds
        store = ResultStore(db)
        try:
            eval_run = store.get_run(run_id)
            if eval_run is None:
                click.echo(f"Error: Run '{run_id}' not found.", err=True)
                sys.exit(1)
        finally:
            store.close()

        ci_result = check_thresholds(eval_run, CIConfig())
        generate_badge(ci_result.pass_rate, output)
        click.echo(f"Badge written to {output}")
