"""The 'suite-hash' command — print a suite's provenance hash (#11)."""

from __future__ import annotations

import click


def register(cli: click.Group, helpers: dict) -> None:
    """Register the suite-hash command on the CLI group."""

    @cli.command(name="suite-hash")
    @click.argument("suite_file", type=click.Path(exists=True))
    def suite_hash(suite_file: str) -> None:
        """Print the reproducibility content-hash of an eval suite (Art.10).

        Pin this in CI to detect dataset drift between approved runs:

          agenteval suite-hash suite.yaml
        """
        from agenteval.loader import load_suite
        from agenteval.provenance import suite_content_hash

        click.echo(suite_content_hash(load_suite(suite_file)))
