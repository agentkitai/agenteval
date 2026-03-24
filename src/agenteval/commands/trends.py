"""The 'trends' command — historical trend analysis and budget guardrails."""

from __future__ import annotations

import sys
from datetime import datetime

import click


def register(cli: click.Group, helpers: dict) -> None:
    """Register the trends command on the CLI group."""

    @cli.command("trends")
    @click.option("--suite", required=True, help="Suite name to analyse.")
    @click.option("--limit", default=20, show_default=True, type=int, help="Max runs to include.")
    @click.option("--budget", default=None, type=click.Path(exists=True), help="YAML budget rules file.")
    @click.option("--db", default="agenteval.db", show_default=True, help="Path to SQLite result store.")
    def trends_cmd(suite: str, limit: int, budget: str | None, db: str) -> None:
        """Show historical trends for a suite and optionally check budget rules.

        Examples:

          agenteval trends --suite my-suite

          agenteval trends --suite my-suite --limit 10 --budget rules.yaml
        """
        from agenteval.store import ResultStore
        from agenteval.trends import check_budgets, compute_trends, load_budget_rules

        store = ResultStore(db)
        try:
            runs = store.list_runs(suite=suite, limit=limit)
        finally:
            store.close()

        if not runs:
            click.echo(f"No runs found for suite '{suite}'.")
            sys.exit(0)

        trend = compute_trends(runs, limit=limit)

        # Header
        click.echo(f"Trend for suite: {suite}  ({len(trend.points)} runs)")
        click.echo("")

        # Table header
        click.echo(
            f"{'Run ID':<14} {'Date':<20} {'Pass%':>7} {'Score':>7} {'Latency':>10} {'Cost':>10}"
        )
        click.echo("-" * 72)

        for pt in trend.points:
            date_str = datetime.fromtimestamp(pt.created_at).strftime("%Y-%m-%d %H:%M") if pt.created_at else "N/A"
            click.echo(
                f"{pt.run_id:<14} {date_str:<20} {pt.pass_rate * 100:>6.1f}% {pt.avg_score:>7.3f} "
                f"{pt.avg_latency_ms:>8.0f}ms ${pt.total_cost:>8.4f}"
            )

        # Direction indicator
        arrow = {"improving": "^ improving", "declining": "v declining", "stable": "= stable"}
        click.echo("")
        click.echo(
            f"Direction: {arrow.get(trend.direction, trend.direction)}  "
            f"(avg pass rate: {trend.avg_pass_rate * 100:.1f}%, "
            f"delta: {trend.pass_rate_delta * 100:+.1f}%)"
        )

        # Budget checks
        if budget:
            rules = load_budget_rules(budget)
            violations = check_budgets(rules, runs)
            if violations:
                click.echo("")
                click.echo("Budget violations:")
                for v in violations:
                    constraint = ""
                    if v.rule.max_value is not None:
                        constraint = f"max={v.rule.max_value}"
                    if v.rule.min_value is not None:
                        constraint = f"min={v.rule.min_value}"
                    click.echo(
                        f"  {v.rule.metric}: {v.actual_value:.4f} ({constraint}) [run {v.run_id}]"
                    )
                sys.exit(1)
            else:
                click.echo("")
                click.echo("Budget checks: all passed.")
