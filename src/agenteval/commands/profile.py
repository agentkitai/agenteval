"""The 'profile' command."""

from __future__ import annotations

import sys
from typing import Optional

import click

from agenteval.store import ResultStore


def register(cli: click.Group, helpers: dict) -> None:
    """Register the profile command on the CLI group."""

    @cli.command("profile")
    @click.option("--run", "run_id", default=None, help="Run ID to profile.")
    @click.option("--trend", is_flag=True, help="Show trend analysis across runs.")
    @click.option("--suite-filter", "suite_filter", default=None, help="Suite name for trend analysis.")
    @click.option("--limit", default=10, show_default=True, help="Max runs for trend analysis.")
    @click.option("--format", "fmt", default="text", type=click.Choice(["text", "json", "csv"]),
                  show_default=True, help="Output format.")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    def profile_cmd(run_id: Optional[str], trend: bool, suite_filter: Optional[str],
                    limit: int, fmt: str, db: str) -> None:
        """Profile a run for latency/cost analysis and outlier detection.

        Examples:

          agenteval profile --run abc123

          agenteval profile --trend --suite-filter my_suite --limit 20

          agenteval profile --run abc123 --format json
        """
        import csv as csv_mod
        import io
        import json as json_mod
        from dataclasses import asdict

        from agenteval.profiler import Profiler, trend_analysis

        if not run_id and not trend:
            click.echo("Error: Specify --run <id> or --trend.", err=True)
            sys.exit(1)

        store = ResultStore(db)
        try:
            if run_id:
                eval_run = store.get_run(run_id)
                if eval_run is None:
                    click.echo(f"Error: Run '{run_id}' not found.", err=True)
                    sys.exit(1)
                profile = Profiler().profile_run(eval_run)

                if fmt == "json":
                    click.echo(json_mod.dumps(asdict(profile), indent=2))
                elif fmt == "csv":
                    buf = io.StringIO()
                    writer = csv_mod.writer(buf)
                    writer.writerow(["case_name", "latency_ms", "cost_usd", "is_outlier", "z_score"])
                    for r in profile.results:
                        writer.writerow([r.case_name, r.latency_ms, f"{r.cost_usd:.4f}",
                                         r.is_outlier, f"{r.z_score:.2f}"])
                    click.echo(buf.getvalue().rstrip())
                else:
                    click.echo(f"\n{'='*60}")
                    click.echo(f"Profile: Run {run_id}")
                    click.echo(f"{'='*60}")
                    click.echo(f"\n{'Case':<30} {'Latency':>10} {'Cost':>10} {'Status'}")
                    click.echo("-" * 65)
                    for r in profile.results:
                        flag = " \u26a0\ufe0f" if r.is_outlier else ""
                        click.echo(f"  {r.case_name:<28} {r.latency_ms:>8}ms ${r.cost_usd:>8.4f} {flag}")
                    click.echo(f"\nMean latency: {profile.mean_latency:.0f}ms  "
                               f"Std: {profile.std_latency:.0f}ms  "
                               f"Total cost: ${profile.total_cost:.4f}  "
                               f"Outliers: {profile.outlier_count}")
                    if profile.recommendations:
                        click.echo("\nRecommendations:")
                        for rec in profile.recommendations:
                            click.echo(f"  \u2022 {rec}")
                    click.echo()

            if trend:
                runs = store.list_runs(suite=suite_filter)[:limit]
                if not runs:
                    click.echo("No runs found for trend analysis.")
                    return
                result = trend_analysis(runs)
                click.echo(f"\nTrend Analysis ({len(runs)} runs)")
                click.echo("-" * 40)
                for case, direction in result.case_trends.items():
                    click.echo(f"  {case:<25} {direction}")
                click.echo(f"\nOverall: {result.overall_direction}  Cost: {result.cost_trend}")
                click.echo()
        finally:
            store.close()
