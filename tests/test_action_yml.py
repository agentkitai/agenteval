"""Validate the GitHub Marketplace action.yml (#14)."""

from pathlib import Path

import yaml

ACTION = Path(__file__).resolve().parent.parent / "action.yml"


def _load():
    with open(ACTION, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_action_yml_is_valid_marketplace_action():
    a = _load()
    assert a["name"] and a["description"]
    assert "branding" in a  # required for Marketplace listing
    assert a["runs"]["using"] == "composite"


def test_required_inputs_match_the_ci_command():
    a = _load()
    inputs = a["inputs"]
    assert inputs["suite"]["required"] is True
    assert inputs["agent"]["required"] is True
    # optional inputs carry defaults
    assert inputs["min-pass-rate"]["default"] == "0.8"
    assert inputs["max-regression"]["default"] == "10"


def test_steps_invoke_agenteval_ci_via_env_not_injection():
    a = _load()
    steps = a["runs"]["steps"]
    run_step = next(s for s in steps if "AgentEval CI gate" in s.get("name", ""))
    body = run_step["run"]
    # entrypoint is the ci command
    assert "agenteval " in body and "ci " in body
    # hardened: inputs come from env vars, NOT `${{ inputs.* }}` in the script body
    assert "${{" not in body
    assert "$SUITE" in body and "$AGENT" in body
    assert set(run_step["env"]) >= {"SUITE", "AGENT", "MIN_PASS_RATE", "MAX_REGRESSION"}
