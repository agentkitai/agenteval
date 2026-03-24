"""The 'examples' command — list available example kits."""

from __future__ import annotations

from pathlib import Path

import click

_KITS = [
    {
        "name": "typescript-agent",
        "description": "Test a TypeScript/Node.js agent via a Python subprocess wrapper",
    },
    {
        "name": "github-actions",
        "description": "CI workflow templates: basic, comparison, and quality gates",
    },
    {
        "name": "docker",
        "description": "Run agenteval in Docker with optional Redis for distributed mode",
    },
]


def _examples_dir() -> Path:
    """Return the path to the examples directory."""
    return Path(__file__).resolve().parents[3] / "examples"


def register(cli: click.Group, helpers: dict) -> None:
    """Register the examples command on the CLI group."""

    _style = helpers["_style"]

    @cli.command("examples")
    def examples_cmd():
        """List available example kits with descriptions and paths."""
        base = _examples_dir()

        click.echo(_style("Available example kits", bold=True))
        click.echo("-" * 60)

        for kit in _KITS:
            name = kit["name"]
            desc = kit["description"]
            kit_path = base / name

            click.echo()
            click.echo(f"  {_style(name, fg='cyan', bold=True)}")
            click.echo(f"    {desc}")
            click.echo(f"    Path: {kit_path}")

        click.echo()
        click.echo("Copy an example directory into your project to get started.")
