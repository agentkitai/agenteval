"""The 'doctor' command — check system readiness and dependency health."""

from __future__ import annotations

import importlib
import os

import click


def register(cli: click.Group, helpers: dict) -> None:
    """Register the doctor command on the CLI group."""

    _style = helpers["_style"]

    @cli.command()
    def doctor():
        """Check system readiness and dependency health."""
        checks = [
            ("pyyaml", "yaml", True, "pip install pyyaml"),
            ("click", "click", True, "pip install click"),
            ("httpx", "httpx", True, "pip install httpx"),
            ("jsonschema", "jsonschema", True, "pip install jsonschema"),
            ("scipy", "scipy", False, "pip install agentevalkit[stats]"),
            ("redis", "redis", False, "pip install agentevalkit[distributed]"),
            ("sentence-transformers", "sentence_transformers", False, "pip install agentevalkit[semantic]"),
            ("langchain", "langchain", False, "pip install agentevalkit[langchain]"),
            ("crewai", "crewai", False, "pip install agentevalkit[crewai]"),
            ("autogen", "pyautogen", False, "pip install agentevalkit[autogen]"),
        ]

        required_ok = 0
        required_total = 0
        optional_available = 0
        optional_total = 0

        click.echo(_style("Dependency checks", bold=True))
        click.echo("-" * 50)

        for pkg_name, import_name, required, install_hint in checks:
            kind = "required" if required else "optional"
            try:
                importlib.import_module(import_name)
                status = _style("OK", fg="green")
                if required:
                    required_ok += 1
                else:
                    optional_available += 1
            except ImportError:
                if required:
                    status = _style("MISSING", fg="red")
                else:
                    status = _style("not installed", fg="yellow")

            if required:
                required_total += 1
            else:
                optional_total += 1

            click.echo(f"  {pkg_name:<25s} [{kind:<8s}] {status}")

        # Check OPENAI_API_KEY
        click.echo()
        click.echo(_style("Environment", bold=True))
        click.echo("-" * 50)
        if os.environ.get("OPENAI_API_KEY"):
            click.echo(f"  {'OPENAI_API_KEY':<25s} {_style('set', fg='green')}")
        else:
            click.echo(f"  {'OPENAI_API_KEY':<25s} {_style('not set', fg='yellow')}")

        # Check agenteval.db writable
        click.echo()
        click.echo(_style("Storage", bold=True))
        click.echo("-" * 50)
        db_path = "agenteval.db"
        try:
            with open(db_path, "a"):
                pass
            click.echo(f"  {db_path:<25s} {_style('writable', fg='green')}")
        except OSError:
            click.echo(f"  {db_path:<25s} {_style('not writable', fg='red')}")

        # Summary
        click.echo()
        click.echo(
            f"Summary: {required_ok}/{required_total} required OK, "
            f"{optional_available}/{optional_total} optional available"
        )
