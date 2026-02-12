"""Import AgentLens sessions as AgentEval test suites.

AgentLens stores agent sessions in SQLite with tables for sessions
and events (LLM calls, tool calls, errors). This importer maps them
to EvalCase/EvalSuite format for replay-based evaluation.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agenteval.models import EvalCase, EvalSuite


class AgentLensImportError(Exception):
    """Raised when import fails."""


# Expected AgentLens schema tables/columns
_REQUIRED_TABLES = {"sessions", "events"}


def _validate_schema(conn: sqlite3.Connection) -> None:
    """Check that the DB has the expected AgentLens tables."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    tables = {row[0] for row in cursor.fetchall()}
    missing = _REQUIRED_TABLES - tables
    if missing:
        raise AgentLensImportError(
            f"Database missing required AgentLens tables: {', '.join(sorted(missing))}. "
            f"Found tables: {', '.join(sorted(tables)) or '(none)'}"
        )


def _load_sessions(
    conn: sqlite3.Connection,
    limit: Optional[int] = None,
    session_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Load sessions from AgentLens DB."""
    query = "SELECT id, agent, input, output, metadata, created_at FROM sessions"
    params: list = []

    if session_ids:
        placeholders = ",".join("?" for _ in session_ids)
        query += f" WHERE id IN ({placeholders})"
        params.extend(session_ids)

    query += " ORDER BY created_at DESC"

    if limit is not None and limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    cursor = conn.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _load_events(conn: sqlite3.Connection, session_id: str) -> List[Dict[str, Any]]:
    """Load events for a session."""
    cursor = conn.execute(
        "SELECT type, data, timestamp FROM events WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


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


def import_agentlens(
    db_path: str,
    suite_name: str = "agentlens-import",
    grader: str = "contains",
    limit: Optional[int] = None,
    session_ids: Optional[List[str]] = None,
) -> EvalSuite:
    """Import sessions from an AgentLens SQLite database as an EvalSuite.

    Args:
        db_path: Path to the AgentLens SQLite database.
        suite_name: Name for the resulting suite.
        grader: Default grader to use for cases.
        limit: Maximum number of sessions to import.
        session_ids: Specific session IDs to import (optional).

    Returns:
        An EvalSuite with cases derived from AgentLens sessions.

    Raises:
        AgentLensImportError: If the DB is missing, corrupt, or has wrong schema.
    """
    from agenteval.loader import VALID_GRADERS

    if grader not in VALID_GRADERS:
        raise AgentLensImportError(
            f"Invalid grader '{grader}'. Valid: {', '.join(sorted(VALID_GRADERS))}"
        )

    path = Path(db_path)
    if not path.exists():
        raise AgentLensImportError(f"Database not found: {db_path}")

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        raise AgentLensImportError(f"Cannot open database: {e}") from e

    try:
        _validate_schema(conn)
        sessions = _load_sessions(conn, limit=limit, session_ids=session_ids)

        if not sessions:
            raise AgentLensImportError("No sessions found in database")

        cases: List[EvalCase] = []
        for session in sessions:
            events = _load_events(conn, str(session["id"]))
            case = _session_to_case(session, events, grader=grader)
            if case is not None:
                cases.append(case)

        if not cases:
            raise AgentLensImportError(
                f"Found {len(sessions)} sessions but none produced valid test cases "
                "(all had empty inputs)"
            )
    except sqlite3.DatabaseError as e:
        raise AgentLensImportError(f"Database error: {e}") from e
    finally:
        conn.close()

    return EvalSuite(
        name=suite_name,
        agent="",
        cases=cases,
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
