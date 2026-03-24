"""The 'list' command."""

from __future__ import annotations

from typing import Optional

import click

from agenteval.store import ResultStore


def register(cli: click.Group, helpers: dict) -> None:
    """Register the list command on the CLI group."""

    @cli.command("list")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    @click.option("--suite-filter", "suite_filter", default=None, help="Filter by suite name.")
    @click.option("--limit", default=20, show_default=True, help="Max number of runs to show.")
    def list_runs(db: str, suite_filter: Optional[str], limit: int) -> None:
        """List past evaluation runs.

        Examples:

          agenteval list

          agenteval list --suite-filter my_suite --limit 5

          agenteval list --db results.db
        """
        import agenteval.cli as _cli_mod
        _fail = _cli_mod._fail

        if limit <= 0:
            _fail("--limit must be positive.")

        store = ResultStore(db)
        try:
            runs = store.list_runs_summary(suite=suite_filter, limit=limit)
        finally:
            store.close()

        if not runs:
            click.echo("No runs found.")
            return

        # Header
        click.echo(f"\n{'ID':<14} {'Suite':<20} {'Passed':<8} {'Failed':<8} {'Rate':<8} {'Created'}")
        click.echo("-" * 80)
        for r in runs:
            s = r.summary
            click.echo(
                f"{r.id:<14} {r.suite:<20} {s.get('passed',0):<8} {s.get('failed',0):<8} "
                f"{s.get('pass_rate',0):<8.0%} {r.created_at[:19]}"
            )
        click.echo()
