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
@click.argument("run_a")
@click.argument("run_b")
@click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
def compare(run_a: str, run_b: str, db: str) -> None:
    """Compare two evaluation runs side-by-side."""
    store = ResultStore(db)
    try:
        a = store.get_run(run_a)
        b = store.get_run(run_b)
    finally:
        store.close()

    if a is None:
        click.echo(f"Error: Run '{run_a}' not found.", err=True)
        sys.exit(1)
    if b is None:
        click.echo(f"Error: Run '{run_b}' not found.", err=True)
        sys.exit(1)

    # Build result maps
    a_map = {r.case_name: r for r in a.results}
    b_map = {r.case_name: r for r in b.results}
    all_cases = list(dict.fromkeys(list(a_map) + list(b_map)))

    click.echo(f"\n{'='*70}")
    click.echo(f"Comparing: {a.id} vs {b.id}")
    click.echo(f"Suites:    {a.suite} vs {b.suite}")
    click.echo(f"{'='*70}")

    click.echo(f"\n{'Case':<30} {a.id:<14} {b.id:<14} {'Change'}")
    click.echo("-" * 70)

    changes = {"improved": 0, "regressed": 0, "unchanged": 0, "new": 0, "removed": 0}
    for case_name in all_cases:
        ra = a_map.get(case_name)
        rb = b_map.get(case_name)

        if ra and rb:
            sa = "PASS" if ra.passed else "FAIL"
            sb = "PASS" if rb.passed else "FAIL"
            if ra.passed == rb.passed:
                change = ""
                changes["unchanged"] += 1
            elif rb.passed and not ra.passed:
                change = click.style("▲ improved", fg="green")
                changes["improved"] += 1
            else:
                change = click.style("▼ regressed", fg="red")
                changes["regressed"] += 1
        elif ra and not rb:
            sa = "PASS" if ra.passed else "FAIL"
            sb = "—"
            change = "removed"
            changes["removed"] += 1
        else:
            sa = "—"
            sb = "PASS" if rb.passed else "FAIL"
            change = "new"
            changes["new"] += 1

        click.echo(f"  {case_name:<28} {sa:<14} {sb:<14} {change}")

    click.echo(f"\nSummary: {changes['improved']} improved, {changes['regressed']} regressed, "
               f"{changes['unchanged']} unchanged")
    if changes["new"] or changes["removed"]:
        click.echo(f"         {changes['new']} new, {changes['removed']} removed")

    # Pass rate comparison
    ar = a.summary.get("pass_rate", 0)
    br = b.summary.get("pass_rate", 0)
    diff = br - ar
    sign = "+" if diff > 0 else ""
    click.echo(f"\nPass rate: {ar:.0%} → {br:.0%} ({sign}{diff:.0%})")
    click.echo()
