"""Baseline storage engine for regression detection.

Stores eval results in a SQLite database with run metadata (commit, branch, timestamp, metrics).
Supports save, show, compare, and auto-update operations.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agenteval.models import EvalResult, EvalRun

_BASELINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT '',
    commit_sha TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    metrics TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS baseline_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    baseline_id INTEGER NOT NULL REFERENCES baselines(id),
    case_name TEXT NOT NULL,
    score REAL NOT NULL,
    passed INTEGER NOT NULL,
    cost_usd REAL,
    latency_ms INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_baseline_suite ON baselines(suite);
CREATE INDEX IF NOT EXISTS idx_baseline_results_id ON baseline_results(baseline_id);
"""


@dataclass
class BaselineEntry:
    """A stored baseline snapshot."""
    id: int
    suite: str
    branch: str
    commit_sha: str
    created_at: str
    metrics: Dict[str, Any]
    results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RegressionResult:
    """Result of a regression check."""
    passed: bool
    regressions: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""


class BaselineStore:
    """SQLite-backed baseline storage."""

    def __init__(self, db_path: str | Path = ".agenteval/baselines.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_BASELINE_SCHEMA)
        return self._conn

    def save_baseline(
        self,
        run: EvalRun,
        branch: str = "",
        commit_sha: str = "",
    ) -> int:
        """Save an eval run as a baseline. Returns the baseline ID."""
        if not branch:
            branch = os.environ.get("GITHUB_REF_NAME", os.environ.get("CI_COMMIT_BRANCH", ""))
        if not commit_sha:
            commit_sha = os.environ.get("GITHUB_SHA", os.environ.get("CI_COMMIT_SHA", ""))

        conn = self._get_conn()
        metrics = {
            "pass_rate": run.summary.get("pass_rate", 0.0),
            "total": run.summary.get("total", 0),
            "passed": run.summary.get("passed", 0),
            "failed": run.summary.get("failed", 0),
            "total_cost_usd": run.summary.get("total_cost_usd", 0.0),
            "avg_latency_ms": run.summary.get("avg_latency_ms", 0.0),
        }

        cursor = conn.execute(
            "INSERT INTO baselines (suite, branch, commit_sha, created_at, metrics) "
            "VALUES (?, ?, ?, ?, ?)",
            (run.suite, branch, commit_sha,
             datetime.now(timezone.utc).isoformat(), json.dumps(metrics)),
        )
        baseline_id = cursor.lastrowid

        for r in run.results:
            conn.execute(
                "INSERT INTO baseline_results "
                "(baseline_id, case_name, score, passed, cost_usd, latency_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (baseline_id, r.case_name, r.score, int(r.passed),
                 r.cost_usd, r.latency_ms),
            )
        conn.commit()
        return baseline_id  # type: ignore[return-value]

    def get_latest_baseline(self, suite: str, branch: str = "") -> Optional[BaselineEntry]:
        """Get the most recent baseline for a suite (optionally filtered by branch)."""
        conn = self._get_conn()
        if branch:
            row = conn.execute(
                "SELECT * FROM baselines WHERE suite = ? AND branch = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (suite, branch),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM baselines WHERE suite = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (suite,),
            ).fetchone()
        if row is None:
            return None
        return self._load_baseline(row)

    def get_baseline(self, baseline_id: int) -> Optional[BaselineEntry]:
        """Get a baseline by ID."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM baselines WHERE id = ?", (baseline_id,)).fetchone()
        if row is None:
            return None
        return self._load_baseline(row)

    def list_baselines(self, suite: Optional[str] = None, limit: int = 20) -> List[BaselineEntry]:
        """List baselines, optionally filtered by suite."""
        conn = self._get_conn()
        if suite:
            rows = conn.execute(
                "SELECT * FROM baselines WHERE suite = ? ORDER BY created_at DESC LIMIT ?",
                (suite, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM baselines ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._load_baseline(r) for r in rows]

    def _load_baseline(self, row: sqlite3.Row) -> BaselineEntry:
        conn = self._get_conn()
        results = conn.execute(
            "SELECT * FROM baseline_results WHERE baseline_id = ?", (row["id"],)
        ).fetchall()
        return BaselineEntry(
            id=row["id"],
            suite=row["suite"],
            branch=row["branch"],
            commit_sha=row["commit_sha"],
            created_at=row["created_at"],
            metrics=json.loads(row["metrics"]),
            results=[
                {
                    "case_name": r["case_name"],
                    "score": r["score"],
                    "passed": bool(r["passed"]),
                    "cost_usd": r["cost_usd"],
                    "latency_ms": r["latency_ms"],
                }
                for r in results
            ],
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "BaselineStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def check_regression(
    run: EvalRun,
    baseline: BaselineEntry,
    threshold: float = 0.05,
    per_metric_thresholds: Optional[Dict[str, float]] = None,
) -> RegressionResult:
    """Compare a run against a baseline and detect regressions.

    Args:
        run: Current eval run.
        baseline: Baseline to compare against.
        threshold: Default maximum allowed score drop (fraction, e.g. 0.05 = 5%).
        per_metric_thresholds: Optional per-case-name thresholds.

    Returns:
        RegressionResult with pass/fail and details.
    """
    if per_metric_thresholds is None:
        per_metric_thresholds = {}

    baseline_scores = {r["case_name"]: r["score"] for r in baseline.results}
    regressions = []

    for result in run.results:
        baseline_score = baseline_scores.get(result.case_name)
        if baseline_score is None:
            continue  # New test, not a regression

        case_threshold = per_metric_thresholds.get(result.case_name, threshold)
        drop = baseline_score - result.score

        if drop > case_threshold:
            regressions.append({
                "case_name": result.case_name,
                "baseline_score": baseline_score,
                "current_score": result.score,
                "drop": drop,
                "threshold": case_threshold,
            })

    passed = len(regressions) == 0
    if regressions:
        names = ", ".join(r["case_name"] for r in regressions)
        summary = f"Regressions detected in {len(regressions)} case(s): {names}"
    else:
        summary = "No regressions detected"

    return RegressionResult(passed=passed, regressions=regressions, summary=summary)


def should_auto_update_baseline(
    auto_baseline: bool = False,
    default_branch: str = "main",
) -> bool:
    """Check if baselines should be auto-updated (running on default branch)."""
    if not auto_baseline:
        return False

    # Check GitHub Actions
    github_ref = os.environ.get("GITHUB_REF_NAME", "")
    if github_ref == default_branch:
        return True

    # Check GitLab CI
    gitlab_branch = os.environ.get("CI_COMMIT_BRANCH", "")
    if gitlab_branch == default_branch:
        return True

    # Check generic CI
    branch = os.environ.get("BRANCH_NAME", os.environ.get("CI_BRANCH", ""))
    if branch == default_branch:
        return True

    return False
