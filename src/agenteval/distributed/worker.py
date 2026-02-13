"""Worker — BRPOP loop that executes eval cases from Redis."""

from __future__ import annotations

import asyncio
import json
import signal
import threading
import uuid
from typing import Optional

from agenteval.models import EvalCase

def _get_redis():
    try:
        import redis
        return redis
    except ImportError:
        raise ImportError(
            "Redis is required for distributed execution. "
            "Install it with: pip install agentevalkit[distributed]"
        )


class Worker:
    """Processes eval tasks from Redis queues."""

    def __init__(self, broker_url: str, concurrency: int = 1) -> None:
        self.broker_url = broker_url
        self.concurrency = concurrency
        self.worker_id = uuid.uuid4().hex[:12]
        redis = _get_redis()
        self._redis = redis.Redis.from_url(broker_url, decode_responses=True)
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None

    def _heartbeat_key(self) -> str:
        return f"agenteval:worker:{self.worker_id}"

    def _send_heartbeat(self) -> None:
        self._redis.setex(self._heartbeat_key(), 60, "alive")

    def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                self._send_heartbeat()
            except Exception:
                pass
            # Sleep in small increments so we can exit quickly
            for _ in range(30):
                if not self._running:
                    break
                import time
                time.sleep(1)

    def start(self) -> None:
        """Start the worker BRPOP loop. Blocks until stop() is called."""
        self._running = True
        self._send_heartbeat()

        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        # Install signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, lambda *_: self.stop())
            except (OSError, ValueError):
                pass  # Can't set signal handler in non-main thread

        while self._running:
            # BRPOP on all task queues (use SCAN to avoid O(N) KEYS)
            keys = [k for k in self._redis.scan_iter("agenteval:tasks:*", count=100)]
            if not keys:
                import time
                time.sleep(1)
                continue

            item = self._redis.brpop(keys, timeout=2)
            if item is None:
                continue

            queue_key, raw = item
            try:
                task = json.loads(raw)
                self._process_task(task)
            except Exception as exc:
                import sys
                print(f"Worker error: {exc}", file=sys.stderr)

    def _process_task(self, task: dict) -> None:
        """Execute a single task and push result to Redis."""
        run_id = task["run_id"]
        agent_ref = task["agent_ref"]
        case_data = task["case"]

        case = EvalCase(
            name=case_data["name"],
            input=case_data["input"],
            expected=case_data["expected"],
            grader=case_data["grader"],
            grader_config=case_data.get("grader_config", {}),
            tags=case_data.get("tags", []),
        )

        from agenteval.adapters import _import_agent
        from agenteval.runner import _run_case

        agent_fn = _import_agent(agent_ref)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_run_case(case, agent_fn, timeout=30.0))
        finally:
            loop.close()

        result_data = {
            "case_name": result.case_name,
            "passed": result.passed,
            "score": result.score,
            "details": result.details,
            "agent_output": result.agent_output,
            "tools_called": result.tools_called,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms,
        }

        result_key = f"agenteval:results:{run_id}"
        self._redis.lpush(result_key, json.dumps(result_data))

    def stop(self) -> None:
        """Signal the worker to stop gracefully."""
        self._running = False
