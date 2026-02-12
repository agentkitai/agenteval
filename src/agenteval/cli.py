"""CLI entry point for AgentEval."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from typing import Optional

import click

from agenteval import __version__
from agenteval.loader import LoadError, load_suite
from agenteval.runner import run_suite
from agenteval.store import ResultStore


@click.group()
@click.version_option(version=__version__, prog_name="agenteval")
def cli() -> None:
    """AgentEval — Testing and evaluation framework for AI agents."""


def _resolve_callable(dotted_path: str):
    """Import and return a callable from a dotted path like 'pkg.mod:func'."""
    # Ensure CWD is in sys.path so local modules can be imported
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    if ":" not in dotted_path:
        raise click.BadParameter(
            f"Agent callable must use 'module:attribute' format, got '{dotted_path}'"
        )
    module_path, attr_name = dotted_path.rsplit(":", 1)
    try:
        mod = importlib.import_module(module_path)
    except ImportError as e:
        raise click.BadParameter(f"Cannot import module '{module_path}': {e}") from e
    try:
        fn = getattr(mod, attr_name)
    except AttributeError:
        raise click.BadParameter(
            f"Module '{module_path}' has no attribute '{attr_name}'"
        )
    if not callable(fn):
        raise click.BadParameter(f"'{dotted_path}' is not callable")
    return fn


@cli.command()
@click.option("--suite", required=True, type=click.Path(exists=True), help="Path to YAML suite file.")
@click.option("--agent", default=None, help="Agent callable as 'module:func'. Overrides suite agent field.")
@click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed per-case output.")
@click.option("--tag", multiple=True, help="Filter cases by tag (repeatable).")
@click.option("--timeout", default=30.0, show_default=True, help="Per-case timeout in seconds.")
def run(suite: str, agent: Optional[str], db: str, verbose: bool, tag: tuple, timeout: float) -> None:
    """Run an evaluation suite against an agent."""
    if timeout <= 0:
        click.echo("Error: --timeout must be positive.", err=True)
        sys.exit(1)

    # Load suite
    try:
        eval_suite = load_suite(suite)
    except LoadError as e:
        click.echo(f"Error loading suite: {e}", err=True)
        sys.exit(1)

    # Filter by tags if specified
    if tag:
        tag_set = set(tag)
        original_count = len(eval_suite.cases)
        eval_suite.cases = [
            c for c in eval_suite.cases
            if tag_set & set(c.tags)
        ]
        if not eval_suite.cases:
            click.echo(
                f"No cases match tags {sorted(tag_set)} (suite has {original_count} cases).",
                err=True,
            )
            sys.exit(1)

    # Resolve agent callable
    agent_ref = agent or eval_suite.agent
    if not agent_ref:
        click.echo("Error: No agent specified. Use --agent or set 'agent' in suite YAML.", err=True)
        sys.exit(1)

    try:
        agent_fn = _resolve_callable(agent_ref)
    except click.BadParameter as e:
        click.echo(f"Error: {e.format_message()}", err=True)
        sys.exit(1)

    # Run
    store = ResultStore(db)
    try:
        eval_run = asyncio.run(
            run_suite(eval_suite, agent_fn, store=store, timeout=timeout)
        )
    except Exception as e:
        click.echo(f"Error during run: {e}", err=True)
        sys.exit(1)
    finally:
        store.close()

    # Print results
    _print_run_results(eval_run, verbose)

    # Exit code
    if eval_run.summary["failed"] > 0:
        sys.exit(1)


def _print_run_results(run, verbose: bool) -> None:
    """Print run results as a formatted table."""
    click.echo(f"\n{'='*60}")
    click.echo(f"Suite: {run.suite}  |  Run: {run.id}")
    click.echo(f"{'='*60}")

    if verbose:
        for r in run.results:
            status = click.style("PASS", fg="green") if r.passed else click.style("FAIL", fg="red")
            click.echo(f"  {status}  {r.case_name} (score={r.score:.2f}, {r.latency_ms}ms)")
            if not r.passed and r.details:
                for k, v in r.details.items():
                    click.echo(f"         {k}: {v}")

    s = run.summary
    click.echo(f"\nTotal: {s['total']}  Passed: {s['passed']}  Failed: {s['failed']}  "
               f"Pass rate: {s['pass_rate']:.0%}")
    if s.get("total_cost_usd"):
        click.echo(f"Cost: ${s['total_cost_usd']:.4f}  Avg latency: {s['avg_latency_ms']:.0f}ms")
    click.echo()


@cli.command("list")
@click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
@click.option("--suite-filter", "suite_filter", default=None, help="Filter by suite name.")
@click.option("--limit", default=20, show_default=True, help="Max number of runs to show.")
def list_runs(db: str, suite_filter: Optional[str], limit: int) -> None:
    """List past evaluation runs."""
    if limit <= 0:
        click.echo("Error: --limit must be positive.", err=True)
        sys.exit(1)

    store = ResultStore(db)
    try:
        runs = store.list_runs_summary(suite=suite_filter)
    finally:
        store.close()

    if not runs:
        click.echo("No runs found.")
        return

    runs = runs[:limit]

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


@cli.command()
@click.argument("run_ids", nargs=-1, required=True)
@click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
@click.option("--alpha", default=0.05, show_default=True, help="Significance level for t-test.")
@click.option("--threshold", default=0.0, show_default=True, help="Min score drop for regression.")
@click.option("--stats/--no-stats", default=True, show_default=True, help="Show statistical details.")
def compare(run_ids: tuple, db: str, alpha: float, threshold: float, stats: bool) -> None:
    """Compare evaluation runs. Give exactly 2 run IDs, or use 'A1,A2 vs B1,B2' for multi-run.

    Examples:
      agenteval compare RUN_A RUN_B
      agenteval compare RUN_A1,RUN_A2 vs RUN_B1,RUN_B2
    """
    from agenteval.compare import ChangeStatus, compare_runs

    # Parse run IDs: support "id1,id2 vs id3,id4" or simple "idA idB"
    tokens = list(run_ids)
    if "vs" in tokens:
        vs_idx = tokens.index("vs")
        base_ids = [i.strip() for t in tokens[:vs_idx] for i in t.split(",") if i.strip()]
        target_ids = [i.strip() for t in tokens[vs_idx + 1:] for i in t.split(",") if i.strip()]
    elif len(tokens) == 2:
        base_ids = [i.strip() for i in tokens[0].split(",") if i.strip()]
        target_ids = [i.strip() for i in tokens[1].split(",") if i.strip()]
    else:
        click.echo("Error: Provide exactly 2 run IDs or use 'ids vs ids' format.", err=True)
        sys.exit(1)

    if not base_ids or not target_ids:
        click.echo("Error: Both base and target must have at least one run ID.", err=True)
        sys.exit(1)

    store = ResultStore(db)
    try:
        base_runs = []
        for rid in base_ids:
            r = store.get_run(rid)
            if r is None:
                click.echo(f"Error: Run '{rid}' not found.", err=True)
                sys.exit(1)
            base_runs.append(r)

        target_runs = []
        for rid in target_ids:
            r = store.get_run(rid)
            if r is None:
                click.echo(f"Error: Run '{rid}' not found.", err=True)
                sys.exit(1)
            target_runs.append(r)
    finally:
        store.close()

    report = compare_runs(base_runs, target_runs, alpha=alpha, regression_threshold=threshold)

    # Print header
    base_label = ",".join(base_ids)
    target_label = ",".join(target_ids)
    click.echo(f"\n{'='*76}")
    click.echo(f"Comparing: {base_label} vs {target_label}")
    click.echo(f"Alpha: {alpha}  Regression threshold: {threshold}")
    click.echo(f"{'='*76}")

    if stats:
        click.echo(f"\n{'Case':<25} {'Base':>8} {'Target':>8} {'Diff':>8} {'p-value':>9} {'Sig':>4} {'Status'}")
        click.echo("-" * 76)
    else:
        click.echo(f"\n{'Case':<25} {'Base':>8} {'Target':>8} {'Status'}")
        click.echo("-" * 56)

    for c in report.cases:
        b_mean = f"{c.base.mean:.3f}" if c.base else "—"
        t_mean = f"{c.target.mean:.3f}" if c.target else "—"

        if c.status == ChangeStatus.REGRESSED:
            status_str = click.style("▼ regressed", fg="red")
        elif c.status == ChangeStatus.IMPROVED:
            status_str = click.style("▲ improved", fg="green")
        elif c.status == ChangeStatus.NEW:
            status_str = "new"
        elif c.status == ChangeStatus.REMOVED:
            status_str = "removed"
        else:
            status_str = ""

        if stats and c.base and c.target:
            sig = "*" if c.significant else ""
            p_str = f"{c.p_value:.4f}" if c.p_value < 1.0 else "—"
            diff_str = f"{c.mean_diff:+.3f}"
            click.echo(
                f"  {c.case_name:<23} {b_mean:>8} {t_mean:>8} {diff_str:>8} "
                f"{p_str:>9} {sig:>4} {status_str}"
            )
        else:
            if stats:
                click.echo(
                    f"  {c.case_name:<23} {b_mean:>8} {t_mean:>8} {'':>8} "
                    f"{'':>9} {'':>4} {status_str}"
                )
            else:
                click.echo(f"  {c.case_name:<23} {b_mean:>8} {t_mean:>8} {status_str}")

    # Summary
    s = report.summary
    click.echo(f"\nSummary: {s.get('improved', 0)} improved, {s.get('regressed', 0)} regressed, "
               f"{s.get('unchanged', 0)} unchanged")
    if s.get("new") or s.get("removed"):
        click.echo(f"         {s.get('new', 0)} new, {s.get('removed', 0)} removed")

    if report.regressions:
        click.echo(click.style(f"\n⚠ {len(report.regressions)} regression(s) detected!", fg="red", bold=True))

    click.echo()
