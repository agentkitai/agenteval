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
@click.option("--parallel", default=1, show_default=True, type=int, help="Max concurrent cases.")
@click.option("--progress/--no-progress", default=None, help="Show progress bar (default: auto-detect TTY).")
def run(suite: str, agent: Optional[str], db: str, verbose: bool, tag: tuple, timeout: float,
        parallel: int, progress: Optional[bool]) -> None:
    """Run an evaluation suite against an agent."""
    if timeout <= 0:
        click.echo("Error: --timeout must be positive.", err=True)
        sys.exit(1)
    if parallel < 1:
        click.echo("Error: --parallel must be >= 1.", err=True)
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

    # Progress bar
    show_progress = progress if progress is not None else sys.stdout.isatty()
    progress_reporter = None
    on_result_cb = None
    if show_progress:
        from agenteval.progress import ProgressReporter
        progress_reporter = ProgressReporter()
        progress_reporter.start(len(eval_suite.cases))

        def on_result_cb(result):
            progress_reporter.update(result.case_name, result.passed)

    # Run
    store = ResultStore(db)
    try:
        eval_run = asyncio.run(
            run_suite(eval_suite, agent_fn, store=store, timeout=timeout,
                      parallel=parallel, on_result=on_result_cb)
        )
    except Exception as e:
        click.echo(f"Error during run: {e}", err=True)
        sys.exit(1)
    finally:
        store.close()
        if progress_reporter is not None:
            progress_reporter.finish()

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
    if not 0.0 <= min_pass_rate <= 1.0:
        click.echo("Error: --min-pass-rate must be between 0.0 and 1.0.", err=True)
        sys.exit(1)
    if max_regression < 0.0 or max_regression > 100.0:
        click.echo("Error: --max-regression must be between 0 and 100.", err=True)
        sys.exit(1)
    from agenteval.ci import CIConfig, check_thresholds

    try:
        eval_suite = load_suite(suite_path)
    except LoadError as e:
        click.echo(f"Error loading suite: {e}", err=True)
        sys.exit(1)

    try:
        agent_fn = _resolve_callable(agent)
    except click.BadParameter as e:
        click.echo(f"Error: {e.format_message()}", err=True)
        sys.exit(1)

    store = ResultStore(db)
    try:
        eval_run = asyncio.run(
            run_suite(eval_suite, agent_fn, store=store, parallel=parallel)
        )

        baseline_run = None
        if baseline:
            baseline_run = store.get_run(baseline)
            if baseline_run is None:
                click.echo(f"Error: Baseline run '{baseline}' not found.", err=True)
                sys.exit(1)
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
    from agenteval.ci import CIConfig, check_thresholds
    from agenteval.formatters.github_comment import format_github_comment
    store = ResultStore(db)
    try:
        eval_run = store.get_run(run_id)
        if eval_run is None:
            click.echo(f"Error: Run '{run_id}' not found.", err=True)
            sys.exit(1)
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
        click.echo("Error: GITHUB_TOKEN, GITHUB_REPOSITORY, and GITHUB_EVENT_PATH must be set.", err=True)
        sys.exit(1)

    import json as _json
    with open(event_path) as f:
        event = _json.load(f)
    pr_number = event.get("pull_request", {}).get("number") or event.get("number")
    if not pr_number:
        click.echo("Error: Could not determine PR number from GITHUB_EVENT_PATH.", err=True)
        sys.exit(1)

    from agenteval.github import GitHubClient
    client = GitHubClient(token, repo, int(pr_number))
    client.post_or_update_comment(comment)
    click.echo(f"Comment posted to {repo}#{pr_number}")


@cli.command("badge")
@click.option("--run", "run_id", required=True, help="Run ID.")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output SVG path.")
@click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
def badge_cmd(run_id: str, output: str, db: str) -> None:
    """Generate a pass-rate badge SVG."""
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


@cli.command("import")
@click.option("--from", "source", required=True, type=click.Choice(["agentlens"]), help="Import source.")
@click.option("--db", required=True, type=click.Path(), help="Path to source database.")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output YAML suite path.")
@click.option("--name", default=None, help="Suite name (defaults to source name).")
@click.option("--grader", default="contains", show_default=True, help="Default grader for imported cases.")
@click.option("--limit", default=None, type=int, help="Max sessions to import.")
def import_cmd(source: str, db: str, output: str, name: Optional[str], grader: str, limit: Optional[int]) -> None:
    """Import agent sessions from external sources as eval suites."""
    if source == "agentlens":
        from agenteval.importers.agentlens import AgentLensImportError
        from agenteval.importers.agentlens import export_suite_yaml, import_agentlens

        suite_name = name or "agentlens-import"
        try:
            suite = import_agentlens(db_path=db, suite_name=suite_name, grader=grader, limit=limit)
        except AgentLensImportError as e:
            click.echo(f"Import error: {e}", err=True)
            sys.exit(1)

        out_path = export_suite_yaml(suite, output)
        click.echo(f"Imported {len(suite.cases)} cases → {out_path}")


@cli.command("import-agentlens")
@click.option("--session", default=None, help="Single session ID to import.")
@click.option("--batch", is_flag=True, help="Batch import multiple sessions.")
@click.option("--server", required=True, help="AgentLens server URL.")
@click.option("--api-key", default=None, help="API key for AgentLens server.")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output YAML suite path.")
@click.option("--filter-tag", multiple=True, help="Filter sessions by tag (batch mode).")
@click.option("--limit", default=50, show_default=True, type=int, help="Max sessions for batch import.")
@click.option("--interactive", is_flag=True, help="Review cases interactively before saving.")
@click.option("--auto-assertions", is_flag=True, help="Auto-generate assertions from session data.")
def import_agentlens_cmd(
    session: Optional[str],
    batch: bool,
    server: str,
    api_key: Optional[str],
    output: str,
    filter_tag: tuple,
    limit: int,
    interactive: bool,
    auto_assertions: bool,
) -> None:
    """Import sessions from an AgentLens server API."""
    from agenteval.importers.agentlens import (
        AgentLensClient,
        AgentLensImportError,
        batch_import,
        export_suite_yaml,
        import_session,
    )

    if not session and not batch:
        click.echo("Error: Specify --session <id> or --batch.", err=True)
        sys.exit(1)

    try:
        client = AgentLensClient(server, api_key=api_key)

        if batch:
            tags = list(filter_tag) if filter_tag else None
            suite = batch_import(client, filter_tags=tags, limit=limit)
        else:
            session_data = client.fetch_session(session)
            case = import_session(session_data)
            cases = [case] if case else []

            if auto_assertions and cases:
                from agenteval.importers.assertions import AssertionGenerator

                for c in cases:
                    assertions = AssertionGenerator.from_session(session_data)
                    if assertions:
                        c.grader_config["assertions"] = assertions

            from agenteval.models import EvalSuite as _EvalSuite
            suite = _EvalSuite(name="agentlens-import", agent="", cases=cases)

        if interactive and suite.cases:
            from agenteval.importers.reviewer import InteractiveReviewer

            reviewer = InteractiveReviewer()
            suite.cases = reviewer.review(suite.cases)

        out_path = export_suite_yaml(suite, output)
        click.echo(f"Imported {len(suite.cases)} cases → {out_path}")

    except AgentLensImportError as e:
        click.echo(f"Import error: {e}", err=True)
        sys.exit(1)
