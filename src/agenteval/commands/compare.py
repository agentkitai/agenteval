"""The 'compare' command."""

from __future__ import annotations

import click

from agenteval.store import ResultStore


def register(cli: click.Group, helpers: dict) -> None:
    """Register the compare command on the CLI group."""

    @cli.command()
    @click.argument("run_ids", nargs=-1, required=True)
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    @click.option("--alpha", default=0.05, show_default=True, help="Significance level for t-test.")
    @click.option("--threshold", default=0.0, show_default=True, help="Min score drop for regression.")
    @click.option("--stats/--no-stats", default=True, show_default=True, help="Show statistical details.")
    @click.option("--gate", default=None, type=click.Path(exists=True), help="Path to gate policy YAML.")
    def compare(run_ids: tuple, db: str, alpha: float, threshold: float, stats: bool, gate: str | None) -> None:
        """Compare evaluation runs. Give exactly 2 run IDs, or use 'A1,A2 vs B1,B2' for multi-run.

        Examples:
          agenteval compare RUN_A RUN_B
          agenteval compare RUN_A1,RUN_A2 vs RUN_B1,RUN_B2
        """
        import agenteval.cli as _cli_mod
        _fail = _cli_mod._fail
        _style = _cli_mod._style

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
            _fail("Provide exactly 2 run IDs or use 'ids vs ids' format.")

        if not base_ids or not target_ids:
            _fail("Both base and target must have at least one run ID.")

        store = ResultStore(db)
        try:
            base_runs = []
            for rid in base_ids:
                r = store.get_run(rid)
                if r is None:
                    _fail(f"Run '{rid}' not found.")
                base_runs.append(r)

            target_runs = []
            for rid in target_ids:
                r = store.get_run(rid)
                if r is None:
                    _fail(f"Run '{rid}' not found.")
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
            b_mean = f"{c.base.mean:.3f}" if c.base else "\u2014"
            t_mean = f"{c.target.mean:.3f}" if c.target else "\u2014"

            if c.status == ChangeStatus.REGRESSED:
                status_str = _style("\u25bc regressed", fg="red")
            elif c.status == ChangeStatus.IMPROVED:
                status_str = _style("\u25b2 improved", fg="green")
            elif c.status == ChangeStatus.NEW:
                status_str = "new"
            elif c.status == ChangeStatus.REMOVED:
                status_str = "removed"
            else:
                status_str = ""

            if stats and c.base and c.target:
                sig = "*" if c.significant else ""
                p_str = f"{c.p_value:.4f}" if c.p_value < 1.0 else "\u2014"
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
            click.echo(_style(f"\n\u26a0 {len(report.regressions)} regression(s) detected!", fg="red", bold=True))

        # Gate policy evaluation
        if gate:
            from agenteval.gates import evaluate_gate, load_gate_policy

            policy = load_gate_policy(gate)
            gate_result = evaluate_gate(policy, target_runs[-1], comparison=report)

            if gate_result.violations:
                click.echo(_style("\nGate policy violations:", fg="red", bold=True))
                for v in gate_result.violations:
                    click.echo(f"  {v.metric}: expected {v.expected}, got {v.actual}")

            if gate_result.passed:
                click.echo(_style("\nGate: PASSED", fg="green", bold=True))
            else:
                click.echo(_style("\nGate: FAILED", fg="red", bold=True))
                click.echo()
                import sys
                sys.exit(1)

        click.echo()
