"""Tests for the runner module."""

import asyncio

import pytest

from agenteval.models import AgentResult, EvalCase, EvalSuite
from agenteval.runner import run_suite
from agenteval.store import ResultStore


def _make_suite(cases=None):
    if cases is None:
        cases = [
            EvalCase(name="c1", input="hello", expected={"output": "hello"},
                     grader="exact"),
        ]
    return EvalSuite(name="test-suite", agent="test-agent", cases=cases)


def _sync_agent(output="hello", **kw):
    def fn(input_text: str) -> AgentResult:
        return AgentResult(output=output, **kw)
    return fn


def _async_agent(output="hello", **kw):
    async def fn(input_text: str) -> AgentResult:
        return AgentResult(output=output, **kw)
    return fn


class TestRunner:
    @pytest.mark.asyncio
    async def test_basic_pass(self):
        run = await run_suite(_make_suite(), _sync_agent("hello"))
        assert run.summary["passed"] == 1
        assert run.results[0].passed is True

    @pytest.mark.asyncio
    async def test_basic_fail(self):
        run = await run_suite(_make_suite(), _sync_agent("wrong"))
        assert run.summary["failed"] == 1
        assert run.results[0].passed is False

    @pytest.mark.asyncio
    async def test_async_agent(self):
        run = await run_suite(_make_suite(), _async_agent("hello"))
        assert run.results[0].passed is True

    @pytest.mark.asyncio
    async def test_agent_timeout(self):
        async def slow_agent(input_text):
            await asyncio.sleep(10)
            return AgentResult(output="late")

        run = await run_suite(_make_suite(), slow_agent, timeout=0.1)
        assert run.results[0].passed is False
        assert "timed out" in run.results[0].details["error"]

    @pytest.mark.asyncio
    async def test_agent_exception(self):
        def bad_agent(input_text):
            raise RuntimeError("boom")

        run = await run_suite(_make_suite(), bad_agent)
        assert run.results[0].passed is False
        assert "boom" in run.results[0].details["error"]

    @pytest.mark.asyncio
    async def test_cost_tracking(self):
        agent = _sync_agent("hello", tokens_in=100, tokens_out=50, cost_usd=0.005)
        run = await run_suite(_make_suite(), agent)
        assert run.results[0].tokens_in == 100
        assert run.results[0].cost_usd == 0.005
        assert run.summary["total_cost_usd"] == 0.005

    @pytest.mark.asyncio
    async def test_latency_patched(self):
        run = await run_suite(_make_suite(), _sync_agent("hello"))
        # Latency is measured; for trivial sync calls it may round to 0
        assert run.results[0].latency_ms >= 0

    @pytest.mark.asyncio
    async def test_multiple_cases(self):
        cases = [
            EvalCase(name="c1", input="a", expected={"output": "a"}, grader="exact"),
            EvalCase(name="c2", input="b", expected={"output": "b"}, grader="exact"),
        ]
        run = await run_suite(_make_suite(cases), _sync_agent("a"))
        assert run.summary["passed"] == 1
        assert run.summary["failed"] == 1

    @pytest.mark.asyncio
    async def test_store_integration(self, tmp_path):
        store = ResultStore(tmp_path / "test.db")
        try:
            run = await run_suite(_make_suite(), _sync_agent("hello"), store=store)
            loaded = store.get_run(run.id)
            assert loaded is not None
            assert loaded.summary["passed"] == 1
        finally:
            store.close()

    @pytest.mark.asyncio
    async def test_custom_run_id(self):
        run = await run_suite(_make_suite(), _sync_agent("hello"), run_id="custom-123")
        assert run.id == "custom-123"

    @pytest.mark.asyncio
    async def test_sync_agent_timeout(self):
        """Sync callables that block must also be timed out."""
        import time as _time

        def slow_sync_agent(input_text):
            _time.sleep(10)
            return AgentResult(output="late")

        run = await run_suite(_make_suite(), slow_sync_agent, timeout=0.2)
        assert run.results[0].passed is False
        assert "timed out" in run.results[0].details["error"]

    @pytest.mark.asyncio
    async def test_summary_stats(self):
        cases = [
            EvalCase(name="c1", input="x", expected={"output": "x"}, grader="exact"),
            EvalCase(name="c2", input="y", expected={"output": "y"}, grader="exact"),
        ]
        agent = _sync_agent("x", tokens_in=10, tokens_out=5, cost_usd=0.01)
        run = await run_suite(_make_suite(cases), agent)
        assert run.summary["total"] == 2
        assert run.summary["pass_rate"] == 0.5
        assert run.summary["total_tokens_in"] == 20
        assert run.summary["avg_latency_ms"] >= 0
