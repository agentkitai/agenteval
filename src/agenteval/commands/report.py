"""The 'report' command."""

from __future__ import annotations

import click

from agenteval.store import ResultStore


def register(cli: click.Group, helpers: dict) -> None:
    """Register the report command on the CLI group."""

    @cli.command()
    @click.argument("run_id")
    @click.option("--format", "fmt", default="json", type=click.Choice(["json", "markdown"]),
                  show_default=True, help="Report format.")
    @click.option("--output", "-o", default=None, type=click.Path(), help="Output file path (default: stdout).")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    def report(run_id: str, fmt: str, output: str | None, db: str) -> None:
        """Generate a report for an evaluation run.

        Examples:

          agenteval report RUN_ID

          agenteval report RUN_ID --format markdown --output report.md
        """
        import agenteval.cli as _cli_mod
        _fail = _cli_mod._fail

        from agenteval.reports import generate_report

        store = ResultStore(db)
        try:
            run = store.get_run(run_id)
            if run is None:
                _fail(f"Run '{run_id}' not found.")
        finally:
            store.close()

        content = generate_report(run, format=fmt)

        if output:
            with open(output, "w") as f:
                f.write(content)
            click.echo(f"Report written to {output}")
        else:
            click.echo(content, nl=False)
