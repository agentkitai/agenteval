"""CLI entry point for AgentEval."""

import click

from agenteval import __version__


@click.group()
@click.version_option(version=__version__, prog_name="agenteval")
def cli() -> None:
    """AgentEval — Testing and evaluation framework for AI agents."""
