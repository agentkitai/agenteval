"""Runner — executes evaluation suites against agent callables."""

from __future__ import annotations

import asyncio
import json
import random
import time
import uuid
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import Callable, Optional, Union

from agenteval.graders import get_grader
from agenteval.models import AgentResult, EvalCase, EvalResult, EvalRun, EvalSuite
from agenteval.store import ResultStore

AgentCallable = Union[
    Callable[[str], AgentResult],
    Callable[[str], Awaitable[AgentResult]],
]
async def _call_agent(fn: AgentCallable, input_text: str, timeout: float) -> AgentResult:
    """Call the agent callable with timeout, handling both sync and async."""
    start = time.perf_counter()
    if asyncio.iscoroutinefunction(fn):
        result = await asyncio.wait_for(fn(input_text), timeout=timeout)
    else:
        # Run sync callables in executor so they don't block the event loop,
        # and enforce timeout on them too.
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, fn, input_text),
            timeout=timeout,
        )
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    if result.latency_ms == 0:
        result.latency_ms = elapsed_ms
    return result
async def _run_case(
    case: EvalCase, agent_fn: AgentCallable, timeout: float,
    grader_cache: dict | None = None,
    retries: int = 0, retry_backoff_ms: int = 1000,
) -> EvalResult:
    """Run a single eval case: call agent, grade, return result."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            agent_result = await _call_agent(agent_fn, case.input, timeout)
        except (asyncio.TimeoutError, ConnectionError) as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(retry_backoff_ms * 2 ** attempt / 1000)
                continue
            # Final attempt failed
            if isinstance(exc, asyncio.TimeoutError):
                return EvalResult(
                    case_name=case.name, passed=False, score=0.0,
                    details={"error": "Agent call timed out", "attempts": attempt + 1},
                    agent_output="", tools_called=[], tokens_in=0,
                    tokens_out=0, cost_usd=None, latency_ms=int(timeout * 1000),
                )
            return EvalResult(
                case_name=case.name, passed=False, score=0.0,
                details={"error": f"Agent error: {exc}", "attempts": attempt + 1},
                agent_output="", tools_called=[], tokens_in=0,
                tokens_out=0, cost_usd=None, latency_ms=0,
            )
        except Exception as exc:
            return EvalResult(
                case_name=case.name, passed=False, score=0.0,
                details={"error": f"Agent error: {exc}", "attempts": attempt + 1},
                agent_output="", tools_called=[], tokens_in=0,
                tokens_out=0, cost_usd=None, latency_ms=0,
            )

        cache_key = (case.grader, json.dumps(case.grader_config, sort_keys=True))
        if grader_cache is not None and cache_key in grader_cache:
            grader = grader_cache[cache_key]
        else:
            grader = get_grader(case.grader, case.grader_config)
            if grader_cache is not None:
                grader_cache[cache_key] = grader
        try:
            grade = await grader.grade(case, agent_result)
        except (asyncio.TimeoutError, ConnectionError) as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(retry_backoff_ms * 2 ** attempt / 1000)
                continue
            return EvalResult(
                case_name=case.name, passed=False, score=0.0,
                details={"error": f"Grader error: {exc}", "attempts": attempt + 1},
                agent_output=agent_result.output, tools_called=agent_result.tools_called,
                tokens_in=agent_result.tokens_in, tokens_out=agent_result.tokens_out,
                cost_usd=agent_result.cost_usd, latency_ms=agent_result.latency_ms,
            )
        except Exception as exc:
            return EvalResult(
                case_name=case.name, passed=False, score=0.0,
                details={"error": f"Grader error: {exc}", "attempts": attempt + 1},
                agent_output=agent_result.output, tools_called=agent_result.tools_called,
                tokens_in=agent_result.tokens_in, tokens_out=agent_result.tokens_out,
                cost_usd=agent_result.cost_usd, latency_ms=agent_result.latency_ms,
            )

        return EvalResult(
            case_name=case.name, passed=grade.passed, score=grade.score,
            details={"reason": grade.reason, "attempts": attempt + 1},
            agent_output=agent_result.output, tools_called=agent_result.tools_called,
            tokens_in=agent_result.tokens_in, tokens_out=agent_result.tokens_out,
            cost_usd=agent_result.cost_usd, latency_ms=agent_result.latency_ms,
        )

    # Should not reach here, but just in case
    return EvalResult(
        case_name=case.name, passed=False, score=0.0,
        details={"error": f"All {retries + 1} attempts failed: {last_exc}", "attempts": retries + 1},
        agent_output="", tools_called=[], tokens_in=0,
        tokens_out=0, cost_usd=None, latency_ms=0,
    )
async def run_suite(
    suite: EvalSuite,
    agent_fn: AgentCallable,
    *,
    store: Optional[ResultStore] = None,
    timeout: float = 30.0,
    run_id: Optional[str] = None,
    parallel: int = 1,
    on_result: Optional[Callable[[EvalResult], None]] = None,
    adapter: Optional[object] = None,
    run_config: dict | None = None,
    retries: int = 0,
    retry_backoff_ms: int = 1000,
) -> EvalRun:
    """Run all cases in a suite and return an EvalRun.

    Args:
        parallel: Max concurrent cases. 1 = sequential (default).
        on_result: Callback fired as each case completes.
    """
    # Set global random seed for deterministic runs when specified in config.
    if run_config and run_config.get("seed") is not None:
        random.seed(run_config["seed"])

    if adapter is not None:
        agent_fn = adapter.invoke  # type: ignore[assignment]

    if parallel < 1:
        raise ValueError("parallel must be >= 1")

    def _fire_callback(result: EvalResult) -> None:
        if on_result is not None:
            try:
                on_result(result)
            except Exception:
                pass  # Don't let callback errors crash the run

    grader_cache: dict = {}

    if parallel == 1:
        # Sequential: preserves original behavior exactly
        results = []
        for case in suite.cases:
            result = await _run_case(case, agent_fn, timeout, grader_cache, retries, retry_backoff_ms)
            _fire_callback(result)
            results.append(result)
    else:
        # Parallel with semaphore
        sem = asyncio.Semaphore(parallel)
        results_by_index: dict[int, EvalResult] = {}

        async def _run_with_sem(index: int, case: EvalCase) -> None:
            async with sem:
                result = await _run_case(case, agent_fn, timeout, grader_cache, retries, retry_backoff_ms)
                results_by_index[index] = result
                _fire_callback(result)

        await asyncio.gather(
            *(_run_with_sem(i, case) for i, case in enumerate(suite.cases))
        )
        results = [results_by_index[i] for i in range(len(suite.cases))]

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    total_cost = sum(r.cost_usd for r in results if r.cost_usd is not None)
    total_tokens_in = sum(r.tokens_in for r in results)
    total_tokens_out = sum(r.tokens_out for r in results)
    avg_latency = sum(r.latency_ms for r in results) / total if total else 0

    run = EvalRun(
        id=run_id or uuid.uuid4().hex[:12],
        suite=suite.name,
        agent_ref=suite.agent,
        config=run_config or {},
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

    if store is not None:
        store.save_run(run)

    return run
