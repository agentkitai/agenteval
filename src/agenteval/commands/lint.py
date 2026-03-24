"""The 'lint' command — validate suite YAML files."""

from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml

from agenteval.loader import VALID_GRADERS


def register(cli: click.Group, helpers: dict) -> None:
    """Register the lint command on the CLI group."""

    _style = helpers["_style"]

    @cli.command()
    @click.option("--suite", required=True, type=click.Path(), help="Path to YAML suite file.")
    def lint(suite: str):
        """Validate a suite YAML file."""
        errors: list[str] = []
        warnings: list[str] = []

        filepath = Path(suite)
        if not filepath.exists():
            click.echo(_style(f"Error: file not found: {suite}", fg="red"), err=True)
            sys.exit(1)

        # Parse YAML
        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            click.echo(_style(f"Error: invalid YAML syntax: {exc}", fg="red"), err=True)
            sys.exit(1)

        if not isinstance(data, dict):
            click.echo(_style("Error: suite file must contain a YAML mapping", fg="red"), err=True)
            sys.exit(1)

        # Required top-level fields
        if "name" not in data:
            errors.append("Missing required field: 'name'")
        if "cases" not in data:
            errors.append("Missing required field: 'cases'")
        else:
            if not isinstance(data["cases"], list):
                errors.append("'cases' must be a list")
            elif len(data["cases"]) == 0:
                errors.append("'cases' must not be empty")
            else:
                _lint_cases(data["cases"], data.get("defaults", {}), errors, warnings)

        # Agent ref format
        agent = data.get("agent", "")
        if agent and ":" not in agent:
            errors.append(
                f"Agent ref '{agent}' must use 'module:attr' format"
            )

        # Print results
        for w in warnings:
            click.echo(_style(f"  warning: {w}", fg="yellow"))
        for e in errors:
            click.echo(_style(f"  error: {e}", fg="red"))

        if errors:
            click.echo(_style(f"\n{len(errors)} error(s), {len(warnings)} warning(s)", fg="red"))
            sys.exit(1)
        else:
            click.echo(_style(f"Suite is valid. {len(warnings)} warning(s).", fg="green"))


def _lint_cases(
    cases: list,
    defaults: dict,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate individual cases."""
    seen_names: set[str] = set()
    default_grader = defaults.get("grader", "exact")

    for i, case in enumerate(cases):
        label = f"Case {i}"
        if not isinstance(case, dict):
            errors.append(f"{label}: must be a mapping")
            continue

        name = case.get("name")
        if not name:
            errors.append(f"{label}: missing required field 'name'")
        else:
            label = f"Case '{name}'"
            if name in seen_names:
                errors.append(f"{label}: duplicate case name")
            seen_names.add(name)

        if "input" not in case:
            errors.append(f"{label}: missing required field 'input'")

        if "expected" not in case:
            warnings.append(f"{label}: missing 'expected' field")

        grader = case.get("grader", default_grader)
        if "grader" not in case:
            warnings.append(f"{label}: no grader specified, using default '{default_grader}'")

        if grader not in VALID_GRADERS:
            errors.append(
                f"{label}: invalid grader '{grader}'. "
                f"Valid: {', '.join(sorted(VALID_GRADERS))}"
            )

        # Grader-specific validation
        expected = case.get("expected", {})
        if isinstance(expected, dict):
            if grader == "tool-check" and "tools_called" not in expected:
                errors.append(f"{label}: grader 'tool-check' requires 'tools_called' in expected")
            if grader == "regex" and "pattern" not in expected:
                errors.append(f"{label}: grader 'regex' requires 'pattern' in expected")
            if grader == "contains" and "contains" not in expected:
                warnings.append(f"{label}: grader 'contains' typically expects 'contains' in expected")
