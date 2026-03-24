"""The 'baseline' command."""

from __future__ import annotations

import sys
from typing import Optional

import click

from agenteval.store import ResultStore


def register(cli: click.Group, helpers: dict) -> None:
    """Register the baseline command on the CLI group."""

    @cli.command("baseline")
    @click.argument("action", type=click.Choice(["save", "show", "list", "compare"]))
    @click.option("--suite", default=None, help="Suite YAML path (for save) or name (for list/show).")
    @click.option("--agent", default=None, help="Agent callable (for save).")
    @click.option("--branch", default="", help="Branch name.")
    @click.option("--commit", "commit_sha", default="", help="Commit SHA.")
    @click.option("--baseline-db", "baseline_db", default=".agenteval/baselines.db", show_default=True,
                  help="Baseline database path.")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    @click.option("--run", "run_id", default=None, help="Run ID to save as baseline.")
    @click.option("--threshold", default=0.05, show_default=True, type=float,
                  help="Regression threshold (fraction).")
    @click.option("--id", "baseline_id", default=None, type=int, help="Baseline ID (for show).")
    def baseline_cmd(action: str, suite: Optional[str], agent: Optional[str],
                     branch: str, commit_sha: str, baseline_db: str, db: str,
                     run_id: Optional[str], threshold: float, baseline_id: Optional[int]) -> None:
        """Manage baselines for regression detection.

        Examples:

          agenteval baseline save --run abc123

          agenteval baseline list --suite my_suite

          agenteval baseline compare --run abc123 --threshold 0.1
        """
        from agenteval.baselines import BaselineStore, check_regression

        bstore = BaselineStore(baseline_db)
        try:
            if action == "save":
                if not run_id:
                    click.echo("Error: --run is required for save.", err=True)
                    sys.exit(1)
                store = ResultStore(db)
                try:
                    eval_run = store.get_run(run_id)
                finally:
                    store.close()
                if eval_run is None:
                    click.echo(f"Error: Run '{run_id}' not found.", err=True)
                    sys.exit(1)
                bid = bstore.save_baseline(eval_run, branch=branch, commit_sha=commit_sha)
                click.echo(f"Baseline saved (id={bid}) for suite '{eval_run.suite}'")

            elif action == "show":
                if baseline_id is not None:
                    entry = bstore.get_baseline(baseline_id)
                elif suite:
                    entry = bstore.get_latest_baseline(suite, branch=branch)
                else:
                    click.echo("Error: --suite or --id required for show.", err=True)
                    sys.exit(1)
                if entry is None:
                    click.echo("No baseline found.")
                    sys.exit(1)
                click.echo(f"Baseline #{entry.id} | Suite: {entry.suite} | Branch: {entry.branch}")
                click.echo(f"Commit: {entry.commit_sha} | Created: {entry.created_at[:19]}")
                click.echo(f"Metrics: pass_rate={entry.metrics.get('pass_rate', 0):.0%}, "
                            f"total={entry.metrics.get('total', 0)}")
                for r in entry.results:
                    status = "PASS" if r["passed"] else "FAIL"
                    click.echo(f"  {status}  {r['case_name']} (score={r['score']:.2f})")

            elif action == "list":
                entries = bstore.list_baselines(suite=suite)
                if not entries:
                    click.echo("No baselines found.")
                    return
                click.echo(f"\n{'ID':<6} {'Suite':<20} {'Branch':<15} {'Pass Rate':<10} {'Created'}")
                click.echo("-" * 70)
                for e in entries:
                    click.echo(f"{e.id:<6} {e.suite:<20} {e.branch:<15} "
                               f"{e.metrics.get('pass_rate', 0):<10.0%} {e.created_at[:19]}")

            elif action == "compare":
                if not run_id:
                    click.echo("Error: --run is required for compare.", err=True)
                    sys.exit(1)
                store = ResultStore(db)
                try:
                    eval_run = store.get_run(run_id)
                finally:
                    store.close()
                if eval_run is None:
                    click.echo(f"Error: Run '{run_id}' not found.", err=True)
                    sys.exit(1)

                if baseline_id is not None:
                    entry = bstore.get_baseline(baseline_id)
                else:
                    entry = bstore.get_latest_baseline(eval_run.suite, branch=branch)

                if entry is None:
                    click.echo("No baseline found for comparison.")
                    sys.exit(1)

                result = check_regression(eval_run, entry, threshold=threshold)
                click.echo(result.summary)
                if not result.passed:
                    for reg in result.regressions:
                        click.echo(f"  \u25bc {reg['case_name']}: {reg['baseline_score']:.2f} \u2192 "
                                   f"{reg['current_score']:.2f} (drop={reg['drop']:.2f})")
                    sys.exit(1)
        finally:
            bstore.close()
