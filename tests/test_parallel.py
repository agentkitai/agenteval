"""Tests for parallel execution, on_result callback, progress bar, and CLI wiring."""

import asyncio
import time
import sys
from unittest.mock import MagicMock, patch

import pytest

from agenteval.models import AgentResult, EvalCase, EvalSuite, EvalResult
from agenteval.runner import run_suite


def _make_suite(n=1):
    cases = [
        EvalCase(name=f"c{i}", input="hello", expected={"output": "hello"}, grader="exact")
        for i in range(n)
    ]
    return EvalSuite(name="test-suite", agent="test-agent", cases=cases)


def _sync_agent(input_text: str) -> AgentResult:
    return AgentResult(output="hello")


# ── B2-S1: Parallel concurrency ──

class TestParallelRunner:
    @pytest.mark.asyncio
    async def test_parallel_default_sequential(self):
        """parallel=1 (default) runs sequentially, same as before."""
        run = await run_suite(_make_suite(3), _sync_agent)
        assert run.summary["passed"] == 3
        assert len(run.results) == 3

    @pytest.mark.asyncio
    async def test_parallel_maintains_order(self):
        """Results are in original case order, not completion order."""
        delays = [0.15, 0.05, 0.10]  # c0 slowest, c1 fastest

        async def delayed_agent(input_text: str) -> AgentResult:
            idx = int(input_text)
            await asyncio.sleep(delays[idx])
            return AgentResult(output="hello")

        cases = [
            EvalCase(name=f"c{i}", input=str(i), expected={"output": "hello"}, grader="exact")
            for i in range(3)
        ]
        suite = EvalSuite(name="order-test", agent="test", cases=cases)
        run = await run_suite(suite, delayed_agent, parallel=3)
        assert [r.case_name for r in run.results] == ["c0", "c1", "c2"]

    @pytest.mark.asyncio
    async def test_parallel_timing(self):
        """5 cases with 0.2s each, parallel=5 should finish in ~0.2s not ~1s."""
        async def slow_agent(input_text: str) -> AgentResult:
            await asyncio.sleep(0.2)
            return AgentResult(output="hello")

        start = time.perf_counter()
        run = await run_suite(_make_suite(5), slow_agent, parallel=5)
        elapsed = time.perf_counter() - start
        assert run.summary["passed"] == 5
        assert elapsed < 0.6  # Should be ~0.2s, allow margin; sequential would be ~1s

    @pytest.mark.asyncio
    async def test_parallel_semaphore_limits(self):
        """Semaphore actually limits concurrency."""
        max_concurrent = 0
        current = 0
        lock = asyncio.Lock()

        async def tracking_agent(input_text: str) -> AgentResult:
            nonlocal max_concurrent, current
            async with lock:
                current += 1
                if current > max_concurrent:
                    max_concurrent = current
            await asyncio.sleep(0.1)
            async with lock:
                current -= 1
            return AgentResult(output="hello")

        await run_suite(_make_suite(6), tracking_agent, parallel=2)
        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_parallel_invalid_value(self):
        """parallel < 1 raises ValueError."""
        with pytest.raises(ValueError, match="parallel must be >= 1"):
            await run_suite(_make_suite(1), _sync_agent, parallel=0)

    @pytest.mark.asyncio
    async def test_parallel_single_is_sequential(self):
        """parallel=1 gives identical results to no parallel arg."""
        run1 = await run_suite(_make_suite(2), _sync_agent)
        run2 = await run_suite(_make_suite(2), _sync_agent, parallel=1)
        assert run1.summary == run2.summary


# ── B2-S2: on_result streaming callback ──

class TestOnResultCallback:
    @pytest.mark.asyncio
    async def test_callback_fires_for_each_case(self):
        results_seen = []
        run = await run_suite(
            _make_suite(3), _sync_agent,
            on_result=lambda r: results_seen.append(r.case_name)
        )
        assert len(results_seen) == 3

    @pytest.mark.asyncio
    async def test_callback_fires_in_parallel(self):
        """Callback fires even in parallel mode."""
        results_seen = []

        async def slow_agent(input_text: str) -> AgentResult:
            await asyncio.sleep(0.05)
            return AgentResult(output="hello")

        run = await run_suite(
            _make_suite(3), slow_agent, parallel=3,
            on_result=lambda r: results_seen.append(r.case_name)
        )
        assert len(results_seen) == 3
        # Final results still in order
        assert [r.case_name for r in run.results] == ["c0", "c1", "c2"]

    @pytest.mark.asyncio
    async def test_callback_none_is_fine(self):
        """on_result=None (default) works without error."""
        run = await run_suite(_make_suite(2), _sync_agent, on_result=None)
        assert run.summary["passed"] == 2


# ── B2-S3: Progress bar ──

class TestProgressReporter:
    def test_fallback_prints(self, capsys):
        """When rich is not available, prints fallback lines."""
        with patch.dict(sys.modules, {"rich": None, "rich.progress": None}):
            from agenteval.progress import ProgressReporter
            # Force re-import won't help since class is already imported,
            # but the ImportError is caught at start() time
            p = ProgressReporter()
            p.start(2)
            p.update("case_a", True)
            p.update("case_b", False)
            p.finish()

        out = capsys.readouterr().out
        assert "[1/2] case_a: ✓" in out
        assert "[2/2] case_b: ✗" in out

    def test_rich_mode(self):
        """When rich is available, uses rich progress."""
        from agenteval.progress import ProgressReporter
        # Just test it doesn't crash — rich may or may not be installed
        p = ProgressReporter()
        p.start(1)
        p.update("test", True)
        p.finish()

    def test_start_resets_count(self):
        """Calling start resets the completed counter."""
        with patch.dict(sys.modules, {"rich": None, "rich.progress": None}):
            from agenteval.progress import ProgressReporter
            p = ProgressReporter()
            p.start(1)
            p.update("a", True)
            p.start(2)  # reset
            p.update("b", True)
            assert p._completed == 1

    def test_finish_idempotent(self):
        """Calling finish multiple times is safe."""
        from agenteval.progress import ProgressReporter
        p = ProgressReporter()
        p.start(1)
        p.update("a", True)
        p.finish()
        p.finish()  # no crash


# ── B2-S4: CLI wiring ──

class TestCLIParallel:
    def test_cli_has_parallel_option(self):
        """The run command accepts --parallel."""
        from click.testing import CliRunner
        from agenteval.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert "--parallel" in result.output

    def test_cli_has_progress_option(self):
        """The run command accepts --progress/--no-progress."""
        from click.testing import CliRunner
        from agenteval.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert "--progress" in result.output
        assert "--no-progress" in result.output
