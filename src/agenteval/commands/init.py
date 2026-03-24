"""The 'init' command — scaffold a new evaluation suite."""

from __future__ import annotations

import click


_EXAMPLE_CASES = {
    "contains": lambda i: {
        "name": f"case-{i}",
        "input": f"Example input {i}",
        "expected": {"contains": "expected substring"},
        "grader": "contains",
    },
    "exact": lambda i: {
        "name": f"case-{i}",
        "input": f"Example input {i}",
        "expected": {"output": "exact expected output"},
        "grader": "exact",
    },
    "regex": lambda i: {
        "name": f"case-{i}",
        "input": f"Example input {i}",
        "expected": {"pattern": r"expected.*pattern"},
        "grader": "regex",
    },
    "tool-check": lambda i: {
        "name": f"case-{i}",
        "input": f"Example input {i}",
        "expected": {"tools_called": [{"tool": "example_tool"}]},
        "grader": "tool-check",
    },
    "llm-judge": lambda i: {
        "name": f"case-{i}",
        "input": f"Example input {i}",
        "expected": {"criteria": "The response should be helpful and accurate."},
        "grader": "llm-judge",
    },
    "custom": lambda i: {
        "name": f"case-{i}",
        "input": f"Example input {i}",
        "expected": {},
        "grader": "custom",
        "grader_config": {"module": "my_graders:grade_func"},
    },
}


def _build_yaml(suite_name: str, agent_ref: str, grader: str, num_cases: int) -> str:
    """Build a YAML string for the suite."""
    import yaml

    case_factory = _EXAMPLE_CASES.get(grader, _EXAMPLE_CASES["contains"])
    cases = [case_factory(i + 1) for i in range(num_cases)]

    suite = {
        "name": suite_name,
        "agent": agent_ref,
        "cases": cases,
    }
    return yaml.dump(suite, default_flow_style=False, sort_keys=False)


def register(cli: click.Group, helpers: dict) -> None:
    """Register the init command on the CLI group."""

    _style = helpers["_style"]

    @cli.command()
    @click.option("--output", "-o", default="suite.yaml", show_default=True,
                  help="Output file path.")
    @click.option("--non-interactive", is_flag=True, help="Use defaults without prompting.")
    def init(output: str, non_interactive: bool):
        """Scaffold a new evaluation suite interactively."""
        if non_interactive:
            suite_name = "my-agent-tests"
            agent_ref = "my_module:run"
            grader = "contains"
            num_cases = 3
        else:
            suite_name = click.prompt("Suite name", default="my-agent-tests")
            agent_ref = click.prompt("Agent ref (module:attr)", default="my_module:run")
            grader = click.prompt(
                "Grader type",
                default="contains",
                type=click.Choice(
                    ["contains", "exact", "regex", "tool-check", "llm-judge", "custom"],
                    case_sensitive=False,
                ),
            )
            num_cases = click.prompt("Number of starter cases", default=3, type=int)

        content = _build_yaml(suite_name, agent_ref, grader, num_cases)

        with open(output, "w") as f:
            f.write(content)

        click.echo(_style(f"Created {output} with {num_cases} cases.", fg="green"))
        click.echo(f"Run: agenteval run --suite {output}")
