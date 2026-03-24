"""The 'coverage' command."""

from __future__ import annotations

import sys
from typing import Optional

import click

from agenteval.loader import LoadError, load_suite
from agenteval.store import ResultStore


def register(cli: click.Group, helpers: dict) -> None:
    """Register the coverage command on the CLI group."""

    @cli.command("coverage")
    @click.option("--suite", required=True, type=click.Path(exists=True), help="Path to YAML suite file.")
    @click.option("--run", "run_id", default=None, help="Run ID (uses latest if not specified).")
    @click.option("--capabilities", default=None, help="Comma-separated declared capabilities.")
    @click.option("--min-coverage", default=0.0, type=float, help="Minimum coverage percentage (0-100).")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    def coverage_cmd(suite: str, run_id: Optional[str], capabilities: Optional[str],
                     min_coverage: float, db: str) -> None:
        """Report capability coverage metrics."""
        import agenteval.cli as _cli_mod
        _style = _cli_mod._style

        from agenteval.capabilities import (
            CoverageConfig,
            check_coverage_threshold,
            compute_coverage,
            format_coverage_report,
        )

        try:
            eval_suite = load_suite(suite)
        except LoadError as e:
            click.echo(f"Error loading suite: {e}", err=True)
            sys.exit(1)

        store = ResultStore(db)
        try:
            if run_id:
                eval_run = store.get_run(run_id)
            else:
                runs = store.list_runs(suite=eval_suite.name)
                eval_run = runs[0] if runs else None
        finally:
            store.close()

        if eval_run is None:
            click.echo("Error: No run found. Specify --run or run the suite first.", err=True)
            sys.exit(1)

        declared = [c.strip() for c in capabilities.split(",")] if capabilities else []
        config = CoverageConfig(declared_capabilities=declared, min_coverage_pct=min_coverage)
        report = compute_coverage(eval_run, eval_suite, config)

        click.echo(format_coverage_report(report))

        if not check_coverage_threshold(report, min_coverage):
            click.echo(_style(f"\n\u2717 Coverage {report.coverage_pct:.0f}% below threshold {min_coverage:.0f}%",
                                   fg="red"))
            sys.exit(1)
