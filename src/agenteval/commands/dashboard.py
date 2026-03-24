"""The 'dashboard' command."""

from __future__ import annotations

import click


def register(cli: click.Group, helpers: dict) -> None:
    """Register the dashboard command on the CLI group."""

    @cli.command()
    @click.option("--port", default=8080, show_default=True, help="Port to serve on.")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    def dashboard(port: int, db: str) -> None:
        """Launch local web dashboard.

        Examples:

          agenteval dashboard

          agenteval dashboard --port 9090 --db results.db
        """
        from agenteval.dashboard.app import start_dashboard

        start_dashboard(db_path=db, port=port)
