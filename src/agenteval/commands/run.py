"""The 'run' command and result printing helper."""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

import click

from agenteval.loader import LoadError, load_suite
from agenteval.profiles import apply_profile, load_profile
from agenteval.runner import run_suite
from agenteval.store import ResultStore


def register(cli: click.Group, helpers: dict) -> None:
    """Register the run command on the CLI group."""

    @cli.command()
    @click.option("--suite", required=True, type=click.Path(exists=True), help="Path to YAML suite file.")
    @click.option("--agent", default=None, help="Agent callable as 'module:func'. Overrides suite agent field.")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    @click.option("--verbose", "-v", is_flag=True, help="Show detailed per-case output.")
    @click.option("--tag", multiple=True, help="Filter cases by tag (repeatable).")
    @click.option("--exclude-tag", multiple=True, help="Exclude cases with matching tag (repeatable).")
    @click.option("--timeout", default=30.0, show_default=True, help="Per-case timeout in seconds.")
    @click.option("--parallel", default=1, show_default=True, type=int, help="Max concurrent cases.")
    @click.option("--progress/--no-progress", default=None, help="Show progress bar (default: auto-detect TTY).")
    @click.option("--adapter", "adapter_name", default=None, help="Adapter name (e.g. 'langchain').")
    @click.option("--retries", default=0, show_default=True, type=int, help="Retry count for transient failures.")
    @click.option("--retry-backoff-ms", default=1000, show_default=True, type=int, help="Base backoff in ms for retries.")
    @click.option("--profile", "profile_path", default=None, type=click.Path(exists=True),
                  help="Path to a YAML run profile for deterministic configuration.")
    @click.option("--workers", default=None, help="Redis URL for distributed execution.")
    @click.option("--worker-timeout", "worker_timeout", default=30, show_default=True, type=int,
                  help="Seconds to wait for workers before falling back to local.")
    @click.option("--report", "report_path", default=None, type=click.Path(),
                  help="Write JSON report to this path after run completes.")
    def run(suite: str, agent: Optional[str], db: str, verbose: bool, tag: tuple, exclude_tag: tuple,
            timeout: float, parallel: int, progress: Optional[bool], adapter_name: Optional[str] = None,
            retries: int = 0, retry_backoff_ms: int = 1000,
            profile_path: Optional[str] = None,
            workers: Optional[str] = None, worker_timeout: int = 30,
            report_path: Optional[str] = None) -> None:
        """Run an evaluation suite against an agent.

        Examples:

          agenteval run --suite suite.yaml --verbose

          agenteval run --suite suite.yaml --agent my_module:fn --tag math --timeout 60

          agenteval run --suite suite.yaml --parallel 4 --progress
        """
        import agenteval.cli as _cli_mod
        _fail = _cli_mod._fail
        _style = _cli_mod._style
        _resolve_callable = _cli_mod._resolve_callable

        def _print_run_results(run, verbose: bool) -> None:
            """Print run results as a formatted table."""
            click.echo(f"\n{'='*60}")
            click.echo(f"Suite: {run.suite}  |  Run: {run.id}")
            click.echo(f"{'='*60}")

            if verbose:
                for r in run.results:
                    label = "PASS" if r.passed else "FAIL"
                    status = _style(f"{label:<6}", fg="green" if r.passed else "red")
                    click.echo(f"  {status} {r.case_name:<30} score={r.score:<6.2f} {r.latency_ms:>6}ms")
                    if not r.passed and r.details:
                        for k, v in r.details.items():
                            click.echo(f"         {k}: {v}")

            s = run.summary
            click.echo(f"\nTotal: {s['total']}  Passed: {s['passed']}  Failed: {s['failed']}  "
                       f"Pass rate: {s['pass_rate']:.0%}")
            if s.get("total_cost_usd"):
                click.echo(f"Cost: ${s['total_cost_usd']:.4f}  Avg latency: {s['avg_latency_ms']:.0f}ms")
            click.echo()

        if timeout <= 0:
            _fail("--timeout must be positive.")
        if parallel < 1:
            _fail("--parallel must be >= 1.")

        # Load suite
        try:
            eval_suite = load_suite(suite)
        except LoadError as e:
            _fail(f"Loading suite: {e}")

        # Apply profile if provided
        _profile = None
        if profile_path:
            _profile = load_profile(profile_path)
            eval_suite = apply_profile(eval_suite, _profile)
            # Profile provides defaults; CLI flags take precedence.
            # Click uses its defaults when the user doesn't supply the flag,
            # so we only override with profile values when the CLI value is
            # still the declared default.
            if timeout == 30.0 and _profile.timeout != 30:
                timeout = float(_profile.timeout)
            if parallel == 1 and _profile.parallel != 1:
                parallel = _profile.parallel
            if retries == 0 and _profile.retries != 0:
                retries = _profile.retries
            if retry_backoff_ms == 1000 and _profile.retry_backoff_ms != 1000:
                retry_backoff_ms = _profile.retry_backoff_ms

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

        # Exclude by tags if specified
        if exclude_tag:
            exclude_set = set(exclude_tag)
            eval_suite.cases = [
                c for c in eval_suite.cases
                if not (exclude_set & set(c.tags))
            ]
            if not eval_suite.cases:
                click.echo("No cases remain after applying --exclude-tag filter.", err=True)
                sys.exit(1)

        # Resolve agent callable
        agent_ref = agent or eval_suite.agent
        if not agent_ref:
            _fail("No agent specified. Use --agent or set 'agent' in suite YAML.")

        try:
            agent_fn = _resolve_callable(agent_ref)
        except click.BadParameter as e:
            _fail(e.format_message())

        # Resolve adapter (CLI --adapter overrides YAML adapter)
        _adapter_name = adapter_name or eval_suite.defaults.get("adapter")
        _adapter_instance = None
        if _adapter_name:
            from agenteval.adapters import get_adapter
            _adapter_instance = get_adapter(_adapter_name, agent=agent_fn)

        # Distributed execution
        if workers:
            from agenteval.distributed.coordinator import Coordinator

            coordinator = Coordinator(workers, timeout=int(timeout * len(eval_suite.cases)),
                                      worker_timeout=worker_timeout)
            try:
                eval_run = coordinator.distribute(eval_suite, agent_ref)
            except Exception as e:
                _fail(f"During distributed run: {e}")
            _print_run_results(eval_run, verbose)
            if eval_run.summary.get("failed", 0) > 0:
                sys.exit(1)
            return

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

        # Build run config metadata
        _run_config = {
            "timeout": timeout,
            "parallel": parallel,
            "adapter": adapter_name,
            "tags": list(tag) if tag else [],
            "verbose": verbose,
        }
        if _profile is not None:
            _run_config["profile"] = profile_path
            if _profile.seed is not None:
                _run_config["seed"] = _profile.seed

        # Run
        store = ResultStore(db)
        try:
            eval_run = asyncio.run(
                run_suite(eval_suite, agent_fn, store=store, timeout=timeout,
                          parallel=parallel, on_result=on_result_cb,
                          adapter=_adapter_instance, run_config=_run_config,
                          retries=retries, retry_backoff_ms=retry_backoff_ms)
            )
        except Exception as e:
            _fail(f"During run: {e}")
        finally:
            store.close()
            if progress_reporter is not None:
                progress_reporter.finish()

        # Print results
        _print_run_results(eval_run, verbose)

        # Generate report if requested
        if report_path:
            from agenteval.reports import generate_report
            content = generate_report(eval_run, format="json")
            with open(report_path, "w") as f:
                f.write(content)
            click.echo(f"Report written to {report_path}")

        # Exit code
        if eval_run.summary["failed"] > 0:
            sys.exit(1)
