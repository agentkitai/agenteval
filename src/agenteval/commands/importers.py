"""The 'import' and 'import-agentlens' commands."""

from __future__ import annotations

import sys
from typing import Optional

import click


def register(cli: click.Group, helpers: dict) -> None:
    """Register the import commands on the CLI group."""

    @cli.command("import")
    @click.option("--from", "source", required=True, type=click.Choice(["agentlens"]), help="Import source.")
    @click.option("--db", required=True, type=click.Path(), help="Path to source database.")
    @click.option("--output", "-o", required=True, type=click.Path(), help="Output YAML suite path.")
    @click.option("--name", default=None, help="Suite name (defaults to source name).")
    @click.option("--grader", default="contains", show_default=True, help="Default grader for imported cases.")
    @click.option("--limit", default=None, type=int, help="Max sessions to import.")
    def import_cmd(source: str, db: str, output: str, name: Optional[str], grader: str, limit: Optional[int]) -> None:
        """Import agent sessions from external sources as eval suites.

        Examples:

          agenteval import --from agentlens --db sessions.db --output suite.yaml

          agenteval import --from agentlens --db sessions.db --output suite.yaml --grader exact --limit 100
        """
        if source == "agentlens":
            from agenteval.importers.agentlens import (
                AgentLensImportError,
                export_suite_yaml,
                import_agentlens,
            )

            suite_name = name or "agentlens-import"
            try:
                suite = import_agentlens(db_path=db, suite_name=suite_name, grader=grader, limit=limit)
            except AgentLensImportError as e:
                click.echo(f"Import error: {e}", err=True)
                sys.exit(1)

            out_path = export_suite_yaml(suite, output)
            click.echo(f"Imported {len(suite.cases)} cases \u2192 {out_path}")

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
            click.echo(f"Imported {len(suite.cases)} cases \u2192 {out_path}")

        except AgentLensImportError as e:
            click.echo(f"Import error: {e}", err=True)
            sys.exit(1)
