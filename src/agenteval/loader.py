"""YAML suite loader for AgentEval."""

from __future__ import annotations

from pathlib import Path

import yaml

from agenteval.models import EvalCase, EvalSuite

VALID_GRADERS = {"exact", "contains", "regex", "tool-check", "llm-judge", "custom"}


class LoadError(Exception):
    """Raised when a suite file cannot be loaded or is invalid."""


def load_suite(path: str) -> EvalSuite:
    """Load an EvalSuite from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        A validated EvalSuite.

    Raises:
        LoadError: If the file is missing, invalid YAML, or fails validation.
    """
    filepath = Path(path)
    if not filepath.exists():
        raise LoadError(f"Suite file not found: {path}")

    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise LoadError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(data, dict):
        raise LoadError(f"Suite file must contain a YAML mapping, got {type(data).__name__}")

    # Required fields
    if "name" not in data:
        raise LoadError("Suite missing required field: 'name'")
    if "cases" not in data:
        raise LoadError("Suite missing required field: 'cases'")
    if not isinstance(data["cases"], list) or len(data["cases"]) == 0:
        raise LoadError("Suite 'cases' must be a non-empty list")

    defaults = data.get("defaults", {})
    if "adapter" in data:
        defaults["adapter"] = data["adapter"]
    default_grader = defaults.get("grader", "exact")
    default_grader_config = defaults.get("grader_config", {})

    cases = []
    for i, case_data in enumerate(data["cases"]):
        if not isinstance(case_data, dict):
            raise LoadError(f"Case {i} must be a mapping")
        if "name" not in case_data:
            raise LoadError(f"Case {i} missing required field: 'name'")
        if "input" not in case_data:
            raise LoadError(f"Case {i} missing required field: 'input'")

        grader = case_data.get("grader", default_grader)
        if grader not in VALID_GRADERS:
            raise LoadError(
                f"Case '{case_data['name']}' has invalid grader '{grader}'. "
                f"Valid graders: {', '.join(sorted(VALID_GRADERS))}"
            )

        cases.append(EvalCase(
            name=case_data["name"],
            input=case_data["input"],
            expected=case_data.get("expected", {}),
            grader=grader,
            grader_config={**default_grader_config, **case_data.get("grader_config", {})},
            tags=case_data.get("tags", []),
        ))

    return EvalSuite(
        name=data["name"],
        agent=data.get("agent", ""),
        cases=cases,
        defaults=defaults,
    )
