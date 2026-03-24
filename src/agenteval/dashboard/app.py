"""Minimal web dashboard server using only the Python standard library."""

from __future__ import annotations

import json
import os
from functools import cached_property
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from agenteval.models import EvalResult, EvalRun
from agenteval.store import ResultStore


def _run_to_dict(run: EvalRun, *, include_results: bool = False) -> Dict[str, Any]:
    """Serialize an EvalRun to a JSON-friendly dict."""
    d: Dict[str, Any] = {
        "id": run.id,
        "suite": run.suite,
        "agent_ref": run.agent_ref,
        "summary": run.summary,
        "created_at": run.created_at,
    }
    if include_results:
        d["results"] = [_result_to_dict(r) for r in run.results]
    return d


def _result_to_dict(r: EvalResult) -> Dict[str, Any]:
    return {
        "case_name": r.case_name,
        "passed": r.passed,
        "score": r.score,
        "details": r.details,
        "agent_output": r.agent_output,
        "tools_called": r.tools_called,
        "tokens_in": r.tokens_in,
        "tokens_out": r.tokens_out,
        "cost_usd": r.cost_usd,
        "latency_ms": r.latency_ms,
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves the dashboard UI and JSON API."""

    store: ResultStore  # class variable, set before serving

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._handle_api()
        else:
            super().do_GET()

    # ------------------------------------------------------------------
    # API routing
    # ------------------------------------------------------------------

    def _handle_api(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        if path == "/api/runs":
            self._api_list_runs(qs)
        elif path.startswith("/api/runs/"):
            run_id = path.split("/")[-1]
            self._api_get_run(run_id)
        elif path == "/api/suites":
            self._api_list_suites()
        elif path == "/api/trends":
            self._api_trends(qs)
        else:
            self._json_response({"error": "not found"}, status=404)

    # ------------------------------------------------------------------
    # API handlers
    # ------------------------------------------------------------------

    def _api_list_runs(self, qs: Dict[str, List[str]]) -> None:
        suite = qs.get("suite", [None])[0]  # type: ignore[list-item]
        limit = int(qs.get("limit", ["50"])[0])
        runs = self.store.list_runs_summary(suite=suite, limit=limit)
        self._json_response([_run_to_dict(r) for r in runs])

    def _api_get_run(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        if run is None:
            self._json_response({"error": "run not found"}, status=404)
            return
        self._json_response(_run_to_dict(run, include_results=True))

    def _api_list_suites(self) -> None:
        conn = self.store._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT suite FROM eval_runs ORDER BY suite"
        ).fetchall()
        self._json_response([row["suite"] for row in rows])

    def _api_trends(self, qs: Dict[str, List[str]]) -> None:
        suite = qs.get("suite", [None])[0]  # type: ignore[list-item]
        limit = int(qs.get("limit", ["20"])[0])
        runs = self.store.list_runs_summary(suite=suite, limit=limit)
        # Return newest-last for charting
        runs.reverse()
        data = []
        for r in runs:
            summary = r.summary if isinstance(r.summary, dict) else {}
            data.append({
                "id": r.id,
                "created_at": r.created_at,
                "pass_rate": summary.get("pass_rate"),
                "total": summary.get("total"),
                "passed": summary.get("passed"),
                "cost_usd": summary.get("cost_usd"),
            })
        self._json_response(data)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _json_response(self, data: Any, *, status: int = 200) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Quieter logging — only show API requests
        if args and isinstance(args[0], str) and "/api/" in args[0]:
            super().log_message(format, *args)


def start_dashboard(db_path: str = "agenteval.db", port: int = 8080) -> None:
    """Start the dashboard HTTP server (blocking)."""
    store = ResultStore(db_path)
    DashboardHandler.store = store
    DashboardHandler.directory = os.path.join(os.path.dirname(__file__), "static")
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"AgentEval Dashboard running at http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard.")
    finally:
        server.server_close()
        store.close()
