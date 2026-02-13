"""Coordinator — distributes eval cases to workers via Redis."""

from __future__ import annotations

import json
import uuid
import warnings
from dataclasses import asdict
from typing import Optional

from agenteval.models import EvalCase, EvalResult, EvalRun, EvalSuite

try:
    import redis
except ImportError:
    raise ImportError(
        "Redis is required for distributed execution. "
        "Install it with: pip install agentevalkit[distributed]"
    )


class Coordinator:
    """Distributes eval suite cases to Redis-backed workers."""

    def __init__(self, broker_url: str, timeout: int = 300, worker_timeout: int = 30) -> None:
        self.broker_url = broker_url
        self.timeout = timeout
        self.worker_timeout = worker_timeout
        self._redis = redis.Redis.from_url(broker_url, decode_responses=True)

    def _has_workers(self) -> bool:
        """Check if any workers have active heartbeats."""
        keys = self._redis.keys("agenteval:worker:*")
        return len(keys) > 0

    def distribute(
        self,
        suite: EvalSuite,
        agent_ref: str,
        *,
        run_id: Optional[str] = None,
    ) -> EvalRun:
        """Distribute suite cases to workers and collect results.

        Falls back to local execution if no workers are available.
        """
        if not self._has_workers():
            warnings.warn("No workers available, falling back to local execution")
            return self._fallback_local(suite, agent_ref, run_id=run_id)

        rid = run_id or uuid.uuid4().hex[:12]
        task_key = f"agenteval:tasks:{rid}"
        result_key = f"agenteval:results:{rid}"

        # Push each case as a task
        for case in suite.cases:
            task = {
                "run_id": rid,
                "agent_ref": agent_ref,
                "case": {
                    "name": case.name,
                    "input": case.input,
                    "expected": case.expected,
                    "grader": case.grader,
                    "grader_config": case.grader_config,
                    "tags": case.tags,
                },
            }
            self._redis.lpush(task_key, json.dumps(task))

        # Collect results
        results: list[EvalResult] = []
        expected = len(suite.cases)
        remaining_timeout = self.timeout

        while len(results) < expected and remaining_timeout > 0:
            wait = min(remaining_timeout, 5)
            item = self._redis.brpop(result_key, timeout=wait)
            if item is not None:
                _, raw = item
                data = json.loads(raw)
                results.append(EvalResult(**data))
            remaining_timeout -= wait

        if len(results) < expected:
            warnings.warn(
                f"Timeout: received {len(results)}/{expected} results"
            )

        return self._build_run(rid, suite, agent_ref, results)

    def _fallback_local(
        self, suite: EvalSuite, agent_ref: str, *, run_id: Optional[str] = None
    ) -> EvalRun:
        """Fall back to local run_suite execution."""
        import asyncio

        from agenteval.adapters import _import_agent
        from agenteval.runner import run_suite

        agent_fn = _import_agent(agent_ref)
        return asyncio.run(run_suite(suite, agent_fn, run_id=run_id))

    @staticmethod
    def _build_run(
        run_id: str, suite: EvalSuite, agent_ref: str, results: list[EvalResult]
    ) -> EvalRun:
        from datetime import datetime, timezone

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        total_cost = sum(r.cost_usd for r in results if r.cost_usd is not None)
        total_tokens_in = sum(r.tokens_in for r in results)
        total_tokens_out = sum(r.tokens_out for r in results)
        avg_latency = sum(r.latency_ms for r in results) / total if total else 0

        return EvalRun(
            id=run_id,
            suite=suite.name,
            agent_ref=agent_ref,
            config={},
            results=results,
            summary={
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": passed / total if total else 0.0,
                "total_cost_usd": total_cost,
                "total_tokens_in": total_tokens_in,
                "total_tokens_out": total_tokens_out,
                "avg_latency_ms": avg_latency,
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        )
