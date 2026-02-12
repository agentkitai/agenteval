"""SQLite result store for AgentEval."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from agenteval.models import EvalResult, EvalRun

_SCHEMA = """
CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    suite TEXT NOT NULL,
    agent_ref TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    summary TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES eval_runs(id),
    case_name TEXT NOT NULL,
    passed INTEGER NOT NULL,
    score REAL NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',
    agent_output TEXT NOT NULL DEFAULT '',
    tools_called TEXT NOT NULL DEFAULT '[]',
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL,
    latency_ms INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_results_run_id ON eval_results(run_id);
"""


class ResultStore:
    """SQLite-backed store for evaluation results."""

    def __init__(self, db_path: str | Path = "agenteval.db") -> None:
        self._db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
        return self._conn

    def save_run(self, run: EvalRun) -> None:
        """Save a complete evaluation run with all results."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO eval_runs (id, suite, agent_ref, config, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run.id, run.suite, run.agent_ref, json.dumps(run.config),
             json.dumps(run.summary), run.created_at),
        )
        for r in run.results:
            conn.execute(
                "INSERT INTO eval_results "
                "(run_id, case_name, passed, score, details, agent_output, "
                "tools_called, tokens_in, tokens_out, cost_usd, latency_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run.id, r.case_name, int(r.passed), r.score,
                 json.dumps(r.details), r.agent_output,
                 json.dumps(r.tools_called), r.tokens_in, r.tokens_out,
                 r.cost_usd, r.latency_ms),
            )
        conn.commit()

    def get_run(self, run_id: str) -> Optional[EvalRun]:
        """Load an evaluation run by ID."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        results = self._load_results(run_id)
        return EvalRun(
            id=row["id"], suite=row["suite"], agent_ref=row["agent_ref"],
            config=json.loads(row["config"]), results=results,
            summary=json.loads(row["summary"]), created_at=row["created_at"],
        )

    def list_runs(self, suite: Optional[str] = None) -> List[EvalRun]:
        """List runs, optionally filtered by suite."""
        conn = self._get_conn()
        if suite:
            rows = conn.execute(
                "SELECT * FROM eval_runs WHERE suite = ? ORDER BY created_at DESC",
                (suite,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM eval_runs ORDER BY created_at DESC"
            ).fetchall()
        runs = []
        for row in rows:
            results = self._load_results(row["id"])
            runs.append(EvalRun(
                id=row["id"], suite=row["suite"], agent_ref=row["agent_ref"],
                config=json.loads(row["config"]), results=results,
                summary=json.loads(row["summary"]), created_at=row["created_at"],
            ))
        return runs

    def list_runs_summary(self, suite: Optional[str] = None) -> List[EvalRun]:
        """List runs with summary only (no individual results loaded)."""
        conn = self._get_conn()
        if suite:
            rows = conn.execute(
                "SELECT * FROM eval_runs WHERE suite = ? ORDER BY created_at DESC",
                (suite,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM eval_runs ORDER BY created_at DESC"
            ).fetchall()
        return [
            EvalRun(
                id=row["id"], suite=row["suite"], agent_ref=row["agent_ref"],
                config=json.loads(row["config"]), results=[],
                summary=json.loads(row["summary"]), created_at=row["created_at"],
            )
            for row in rows
        ]

    def _load_results(self, run_id: str) -> List[EvalResult]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM eval_results WHERE run_id = ?", (run_id,)
        ).fetchall()
        return [
            EvalResult(
                case_name=r["case_name"], passed=bool(r["passed"]),
                score=r["score"], details=json.loads(r["details"]),
                agent_output=r["agent_output"],
                tools_called=json.loads(r["tools_called"]),
                tokens_in=r["tokens_in"], tokens_out=r["tokens_out"],
                cost_usd=r["cost_usd"], latency_ms=r["latency_ms"],
            )
            for r in rows
        ]

    def __enter__(self) -> "ResultStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
