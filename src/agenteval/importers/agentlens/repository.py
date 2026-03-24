"""SQLite query/schema logic for AgentLens database imports."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from agenteval.importers.agentlens.mapper import (
    AgentLensImportError,
    _session_to_case,
)
from agenteval.models import EvalCase, EvalSuite

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
