"""The 'evidence' command — EU AI Act testing-evidence for a run (#8)."""

from __future__ import annotations

import json

import click

from agenteval.store import ResultStore


def register(cli: click.Group, helpers: dict) -> None:
    """Register the evidence command on the CLI group."""

    @cli.command()
    @click.argument("run_id")
    @click.option("--format", "fmt", default="json", type=click.Choice(["json", "markdown"]),
                  show_default=True, help="Output format.")
    @click.option("--output", "-o", default=None, type=click.Path(), help="Output file path (default: stdout).")
    @click.option("--agent-id", default=None, help="Bind the evidence to this agent id (default: the run's agent_ref).")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    def evidence(run_id: str, fmt: str, output: str | None, agent_id: str | None, db: str) -> None:
        """Produce EU AI Act (Art.11 / Annex IV) testing evidence for a run.

        Identity-bound + tamper-evident (SHA-256 content hash). Not a conformity
        certificate — the verifiable testing-evidence artifact a GRC tool/auditor
        references.

        Examples:

          agenteval evidence RUN_ID

          agenteval evidence RUN_ID --format markdown -o evidence.md
        """
        import agenteval.cli as _cli_mod
        _fail = _cli_mod._fail

        from agenteval.eu_ai_act import build_testing_evidence, render_markdown

        store = ResultStore(db)
        try:
            run = store.get_run(run_id)
            if run is None:
                _fail(f"Run '{run_id}' not found.")
        finally:
            store.close()

        assert run is not None  # _fail() raises; narrows the Optional for type-checkers
        ev = build_testing_evidence(run, agent_id=agent_id)
        rendered = render_markdown(ev) if fmt == "markdown" else json.dumps(ev, indent=2)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(rendered)
            click.echo(f"Wrote {fmt} testing evidence to {output}")
        else:
            click.echo(rendered)
