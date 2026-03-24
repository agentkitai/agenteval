"""Session-to-case conversion logic and YAML export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agenteval.models import EvalCase, EvalSuite


class AgentLensImportError(Exception):
    """Raised when import fails."""


def import_session(session_data: Dict[str, Any], grader: str = "contains") -> Optional[EvalCase]:
    """Convert a session dict (from API or other source) to an EvalCase.

    The session_data dict should have keys: id, agent, input, output, events.
    Returns None if the session has no usable input.
    """
    events = session_data.get("events") or []
    return _session_to_case(session_data, events, grader=grader)


def _parse_json_field(value: Any) -> Any:
    """Safely parse a JSON string field, returning empty dict on failure."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _session_to_case(
    session: Dict[str, Any],
    events: List[Dict[str, Any]],
    grader: str = "contains",
) -> Optional[EvalCase]:
    """Convert an AgentLens session + events to an EvalCase.

    Returns None if the session has no usable input/output.
    """
    input_text = session.get("input") or ""
    output_text = session.get("output") or ""

    if not input_text.strip():
        return None

    # Extract tool calls from events
    tools_called = []
    llm_calls = 0
    error_count = 0

    for event in events:
        event_type = event.get("type", "")
        event_data = _parse_json_field(event.get("data"))

        if event_type == "tool_call":
            tool_name = event_data.get("tool") or event_data.get("name", "unknown")
            tools_called.append(tool_name)
        elif event_type == "llm_call":
            llm_calls += 1
        elif event_type == "error":
            error_count += 1

    # Build expected based on what we have
    expected: Dict[str, Any] = {}
    if output_text.strip():
        expected["output"] = output_text.strip()
    if tools_called:
        expected["tools"] = tools_called

    # Build case name from session ID
    session_id = str(session.get("id", "unknown"))
    agent_name = session.get("agent") or "agent"
    case_name = f"{agent_name}_{session_id[:8]}"

    # Determine grader
    if tools_called and grader == "contains":
        effective_grader = "tool-check"
    else:
        effective_grader = grader

    tags = ["imported", "agentlens"]
    if error_count > 0:
        tags.append("has-errors")

    metadata: Dict[str, Any] = {}
    if llm_calls:
        metadata["llm_calls"] = llm_calls
    if error_count:
        metadata["error_count"] = error_count

    grader_config: Dict[str, Any] = {}
    if metadata:
        grader_config["metadata"] = metadata

    return EvalCase(
        name=case_name,
        input=input_text.strip(),
        expected=expected,
        grader=effective_grader,
        grader_config=grader_config,
        tags=tags,
    )


def export_suite_yaml(suite: EvalSuite, output_path: str) -> str:
    """Export an EvalSuite to YAML file.

    Args:
        suite: The suite to export.
        output_path: Path for the output YAML file.

    Returns:
        The absolute path of the written file.
    """
    data = {
        "name": suite.name,
        "agent": suite.agent or "",
        "cases": [],
    }
    if suite.defaults:
        data["defaults"] = suite.defaults

    for case in suite.cases:
        case_data: Dict[str, Any] = {
            "name": case.name,
            "input": case.input,
        }
        if case.expected:
            case_data["expected"] = case.expected
        if case.grader:
            case_data["grader"] = case.grader
        if case.grader_config:
            case_data["grader_config"] = case.grader_config
        if case.tags:
            case_data["tags"] = case.tags
        data["cases"].append(case_data)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    return str(out.resolve())
