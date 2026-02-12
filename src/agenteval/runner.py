"""Runner — executes evaluation suites against agent callables."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional, Union

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
    result_obj = fn(input_text)
    if asyncio.iscoroutine(result_obj) or asyncio.isfuture(result_obj):
        result = await asyncio.wait_for(result_obj, timeout=timeout)
    else:
        result = result_obj  # type: ignore[assignment]
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    if result.latency_ms == 0:
        result.latency_ms = elapsed_ms
    return result
async def _run_case(
    case: EvalCase, agent_fn: AgentCallable, timeout: float
) -> EvalResult:
    """Run a single eval case: call agent, grade, return result."""
    try:
        agent_result = await _call_agent(agent_fn, case.input, timeout)
    except asyncio.TimeoutError:
        return EvalResult(
            case_name=case.name, passed=False, score=0.0,
            details={"error": "Agent call timed out"},
            agent_output="", tools_called=[], tokens_in=0,
            tokens_out=0, cost_usd=None, latency_ms=int(timeout * 1000),
        )
    except Exception as exc:
        return EvalResult(
            case_name=case.name, passed=False, score=0.0,
            details={"error": f"Agent error: {exc}"},
            agent_output="", tools_called=[], tokens_in=0,
            tokens_out=0, cost_usd=None, latency_ms=0,
        )

    grader = get_grader(case.grader, case.grader_config)
    try:
        grade = await grader.grade(case, agent_result)
    except Exception as exc:
        return EvalResult(
            case_name=case.name, passed=False, score=0.0,
            details={"error": f"Grader error: {exc}"},
            agent_output=agent_result.output, tools_called=agent_result.tools_called,
            tokens_in=agent_result.tokens_in, tokens_out=agent_result.tokens_out,
            cost_usd=agent_result.cost_usd, latency_ms=agent_result.latency_ms,
        )

    return EvalResult(
        case_name=case.name, passed=grade.passed, score=grade.score,
        details={"reason": grade.reason},
        agent_output=agent_result.output, tools_called=agent_result.tools_called,
        tokens_in=agent_result.tokens_in, tokens_out=agent_result.tokens_out,
        cost_usd=agent_result.cost_usd, latency_ms=agent_result.latency_ms,
    )
async def run_suite(
    suite: EvalSuite,
    agent_fn: AgentCallable,
    *,
    store: Optional[ResultStore] = None,
    timeout: float = 30.0,
    run_id: Optional[str] = None,
) -> EvalRun:
    """Run all cases in a suite and return an EvalRun."""
    results = []
    for case in suite.cases:
        result = await _run_case(case, agent_fn, timeout)
        results.append(result)

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

    if store is not None:
        store.save_run(run)

    return run
