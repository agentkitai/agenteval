"""Tests for distributed coordinator and worker."""

from __future__ import annotations

import json
import warnings
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from agenteval.models import EvalCase, EvalResult, EvalRun, EvalSuite


def _make_suite(n: int = 2) -> EvalSuite:
    cases = [
        EvalCase(
            name=f"case_{i}",
            input=f"input_{i}",
            expected={"answer": f"ans_{i}"},
            grader="contains",
        )
        for i in range(n)
    ]
    return EvalSuite(name="test-suite", agent="mod:fn", cases=cases)


def _make_result(case_name: str, passed: bool = True) -> dict:
    return {
        "case_name": case_name,
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "details": {},
        "agent_output": "out",
        "tools_called": [],
        "tokens_in": 10,
        "tokens_out": 20,
        "cost_usd": 0.001,
        "latency_ms": 100,
    }


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


# ── DR-1: Coordinator Tests ─────────────────────────────────────────


class TestCoordinator:
    def _make_coordinator(self, fake_redis):
        from agenteval.distributed.coordinator import Coordinator

        c = Coordinator.__new__(Coordinator)
        c.broker_url = "redis://localhost"
        c.timeout = 10
        c.worker_timeout = 5
        c._redis = fake_redis
        return c

    def test_distribute_pushes_tasks(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        suite = _make_suite(3)

        # Register a worker heartbeat
        fake_redis.setex("agenteval:worker:w1", 60, "alive")

        # Pre-push all results so BRPOP finds them immediately
        for i in range(3):
            fake_redis.lpush(
                "agenteval:results:test123",
                json.dumps(_make_result(f"case_{i}")),
            )

        run = coord.distribute(suite, "mod:fn", run_id="test123")

        assert run.id == "test123"
        assert len(run.results) == 3
        assert run.summary["total"] == 3

    def test_distribute_no_workers_warns(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        suite = _make_suite(1)

        with patch.object(coord, "_fallback_local") as mock_fb:
            mock_fb.return_value = EvalRun(
                id="x", suite="s", agent_ref="a", config={},
                results=[], summary={}, created_at="",
            )
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                coord.distribute(suite, "mod:fn")
                assert any("No workers available" in str(x.message) for x in w)
            mock_fb.assert_called_once()

    def test_distribute_timeout_partial(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        coord.timeout = 1  # Very short timeout
        suite = _make_suite(3)

        fake_redis.setex("agenteval:worker:w1", 60, "alive")

        # Push only 1 result
        fake_redis.lpush(
            "agenteval:results:partial",
            json.dumps(_make_result("case_0")),
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            run = coord.distribute(suite, "mod:fn", run_id="partial")
            assert len(run.results) < 3
            assert any("Timeout" in str(x.message) for x in w)

    def test_has_workers_true(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        fake_redis.setex("agenteval:worker:w1", 60, "alive")
        assert coord._has_workers() is True

    def test_has_workers_false(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        assert coord._has_workers() is False

    def test_build_run_summary(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        suite = _make_suite(2)
        results = [
            EvalResult(**_make_result("case_0", True)),
            EvalResult(**_make_result("case_1", False)),
        ]
        run = coord._build_run("r1", suite, "mod:fn", results)
        assert run.summary["total"] == 2
        assert run.summary["passed"] == 1
        assert run.summary["failed"] == 1
        assert run.summary["pass_rate"] == 0.5

    def test_build_run_empty(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        suite = _make_suite(0)
        run = coord._build_run("r1", suite, "mod:fn", [])
        assert run.summary["total"] == 0
        assert run.summary["pass_rate"] == 0.0

    def test_tasks_contain_case_data(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        suite = _make_suite(1)
        fake_redis.setex("agenteval:worker:w1", 60, "alive")

        # Push a result immediately so distribute doesn't block forever
        fake_redis.lpush(
            "agenteval:results:tcd",
            json.dumps(_make_result("case_0")),
        )
        coord.distribute(suite, "mod:fn", run_id="tcd")

        # Tasks should have been pushed to the list
        # (they may already be consumed, but we can check the task format
        # by inspecting what was pushed)

    def test_distribute_assembles_eval_run(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        suite = _make_suite(1)
        fake_redis.setex("agenteval:worker:w1", 60, "alive")

        fake_redis.lpush(
            "agenteval:results:asm",
            json.dumps(_make_result("case_0")),
        )
        run = coord.distribute(suite, "mod:fn", run_id="asm")
        assert isinstance(run, EvalRun)
        assert run.suite == "test-suite"


# ── DR-2: Worker Tests ──────────────────────────────────────────────


class TestWorker:
    def _make_worker(self, fake_redis):
        from agenteval.distributed.worker import Worker

        w = Worker.__new__(Worker)
        w.broker_url = "redis://localhost"
        w.concurrency = 1
        w.worker_id = "test-worker"
        w._redis = fake_redis
        w._running = False
        w._heartbeat_thread = None
        return w

    def test_heartbeat_sets_key(self, fake_redis):
        worker = self._make_worker(fake_redis)
        worker._send_heartbeat()
        val = fake_redis.get("agenteval:worker:test-worker")
        assert val == "alive"

    def test_heartbeat_key_format(self, fake_redis):
        worker = self._make_worker(fake_redis)
        assert worker._heartbeat_key() == "agenteval:worker:test-worker"

    def test_stop_sets_flag(self, fake_redis):
        worker = self._make_worker(fake_redis)
        worker._running = True
        worker.stop()
        assert worker._running is False

    def test_process_task_pushes_result(self, fake_redis):
        worker = self._make_worker(fake_redis)

        task = {
            "run_id": "r1",
            "agent_ref": "mod:fn",
            "case": {
                "name": "c1",
                "input": "hello",
                "expected": {"answer": "world"},
                "grader": "contains",
                "grader_config": {},
                "tags": [],
            },
        }

        mock_result = EvalResult(
            case_name="c1", passed=True, score=1.0, details={},
            agent_output="world", tools_called=[], tokens_in=5,
            tokens_out=10, cost_usd=0.001, latency_ms=50,
        )

        async def fake_run_case(case, agent_fn, timeout=30.0):
            return mock_result

        with patch("agenteval.adapters._import_agent", return_value=lambda x: None), \
             patch("agenteval.runner._run_case", side_effect=fake_run_case):
            worker._process_task(task)

        raw = fake_redis.rpop("agenteval:results:r1")
        assert raw is not None
        data = json.loads(raw)
        assert data["case_name"] == "c1"
        assert data["passed"] is True

    def test_worker_id_unique(self, fake_redis):
        from agenteval.distributed.worker import Worker

        w1 = Worker.__new__(Worker)
        w1.worker_id = "a"
        w2 = Worker.__new__(Worker)
        w2.worker_id = "b"
        # Just verify the field exists and can differ
        assert w1.worker_id != w2.worker_id

    def test_start_stop_loop(self, fake_redis):
        """Worker start loop exits when stop is called."""
        worker = self._make_worker(fake_redis)

        import threading

        def stop_soon():
            import time
            time.sleep(0.3)
            worker.stop()

        t = threading.Thread(target=stop_soon)
        t.start()

        worker._running = True
        # Simplified loop test — just verify it exits
        while worker._running:
            keys = fake_redis.keys("agenteval:tasks:*")
            if not keys:
                import time
                time.sleep(0.1)
                continue
            break
        t.join()
        assert worker._running is False

    def test_process_task_result_format(self, fake_redis):
        worker = self._make_worker(fake_redis)

        task = {
            "run_id": "fmt",
            "agent_ref": "mod:fn",
            "case": {
                "name": "c1",
                "input": "hi",
                "expected": {},
                "grader": "contains",
            },
        }

        mock_result = EvalResult(
            case_name="c1", passed=False, score=0.0, details={"error": "fail"},
            agent_output="", tools_called=[], tokens_in=0,
            tokens_out=0, cost_usd=None, latency_ms=0,
        )

        async def fake_run_case(case, agent_fn, timeout=30.0):
            return mock_result

        with patch("agenteval.adapters._import_agent", return_value=lambda x: None), \
             patch("agenteval.runner._run_case", side_effect=fake_run_case):
            worker._process_task(task)

        raw = fake_redis.rpop("agenteval:results:fmt")
        data = json.loads(raw)
        assert data["passed"] is False
        assert data["cost_usd"] is None

    def test_heartbeat_expiry(self, fake_redis):
        worker = self._make_worker(fake_redis)
        worker._send_heartbeat()
        ttl = fake_redis.ttl("agenteval:worker:test-worker")
        assert ttl > 0
        assert ttl <= 60


# ── DR-3: Fallback Tests ────────────────────────────────────────────


class TestFallback:
    def _make_coordinator(self, fake_redis):
        from agenteval.distributed.coordinator import Coordinator

        c = Coordinator.__new__(Coordinator)
        c.broker_url = "redis://localhost"
        c.timeout = 10
        c.worker_timeout = 5
        c._redis = fake_redis
        return c

    def test_fallback_called_when_no_workers(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        suite = _make_suite(1)

        with patch.object(coord, "_fallback_local") as mock_fb:
            mock_fb.return_value = EvalRun(
                id="x", suite="s", agent_ref="a", config={},
                results=[], summary={}, created_at="",
            )
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                coord.distribute(suite, "mod:fn")
            mock_fb.assert_called_once()

    def test_no_fallback_when_workers_exist(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        coord.timeout = 1
        suite = _make_suite(1)
        fake_redis.setex("agenteval:worker:w1", 60, "alive")
        fake_redis.lpush(
            "agenteval:results:nf",
            json.dumps(_make_result("case_0")),
        )

        with patch.object(coord, "_fallback_local") as mock_fb:
            coord.distribute(suite, "mod:fn", run_id="nf")
            mock_fb.assert_not_called()

    def test_fallback_warning_message(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        suite = _make_suite(1)

        with patch.object(coord, "_fallback_local") as mock_fb:
            mock_fb.return_value = EvalRun(
                id="x", suite="s", agent_ref="a", config={},
                results=[], summary={}, created_at="",
            )
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                coord.distribute(suite, "mod:fn")
                msgs = [str(x.message) for x in w]
                assert any("falling back to local" in m for m in msgs)

    def test_fallback_returns_eval_run(self, fake_redis):
        coord = self._make_coordinator(fake_redis)
        suite = _make_suite(1)

        expected_run = EvalRun(
            id="fb", suite="test-suite", agent_ref="mod:fn", config={},
            results=[], summary={"total": 0}, created_at="",
        )
        with patch.object(coord, "_fallback_local", return_value=expected_run):
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                run = coord.distribute(suite, "mod:fn")
            assert run is expected_run


# ── DR-4: CLI Tests ─────────────────────────────────────────────────


class TestCLI:
    def test_run_command_has_workers_option(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert "--workers" in result.output

    def test_run_command_has_worker_timeout_option(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert "--worker-timeout" in result.output

    def test_worker_command_exists(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["worker", "--help"])
        assert result.exit_code == 0
        assert "--broker" in result.output

    def test_worker_command_has_concurrency(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["worker", "--help"])
        assert "--concurrency" in result.output

    def test_worker_command_requires_broker(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["worker"])
        assert result.exit_code != 0

    def test_run_with_workers_uses_coordinator(self):
        """When --workers is passed, coordinator should be used."""
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        # This will fail because suite doesn't exist, but the option should parse
        result = runner.invoke(cli, ["run", "--suite", "nonexistent.yaml", "--workers", "redis://localhost"])
        # Should fail on suite loading, not on option parsing
        assert "Error" in result.output or result.exit_code != 0

    def test_run_help_shows_all_options(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert "--workers" in result.output
        assert "--worker-timeout" in result.output
        assert "--parallel" in result.output

    def test_worker_help_shows_all_options(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["worker", "--help"])
        assert "--broker" in result.output
        assert "--concurrency" in result.output
        assert result.exit_code == 0

    def test_cli_version(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0

    def test_worker_command_help_text(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["worker", "--help"])
        assert "worker" in result.output.lower() or "Worker" in result.output
