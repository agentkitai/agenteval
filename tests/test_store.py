"""Tests for SQLite result store."""

import pytest

from agenteval.models import EvalResult, EvalRun
from agenteval.store import ResultStore


def _make_result(**kw):
    defaults = dict(
        case_name="test-case", passed=True, score=1.0,
        details={"reason": "ok"}, agent_output="hello",
        tools_called=[], tokens_in=10, tokens_out=20,
        cost_usd=0.001, latency_ms=150,
    )
    defaults.update(kw)
    return EvalResult(**defaults)


def _make_run(run_id="run-1", results=None):
    return EvalRun(
        id=run_id, suite="my-suite", agent_ref="my-agent",
        config={"key": "val"}, results=results or [_make_result()],
        summary={"total": 1, "passed": 1}, created_at="2026-01-01T00:00:00Z",
    )


@pytest.fixture
def store(tmp_path):
    s = ResultStore(tmp_path / "test.db")
    yield s
    s.close()


class TestResultStore:
    def test_save_and_get_run(self, store):
        run = _make_run()
        store.save_run(run)
        loaded = store.get_run("run-1")
        assert loaded is not None
        assert loaded.id == "run-1"
        assert loaded.suite == "my-suite"
        assert len(loaded.results) == 1
        assert loaded.results[0].passed is True
        assert loaded.results[0].cost_usd == 0.001

    def test_get_run_not_found(self, store):
        assert store.get_run("nonexistent") is None

    def test_list_runs(self, store):
        store.save_run(_make_run("run-1"))
        store.save_run(_make_run("run-2"))
        runs = store.list_runs()
        assert len(runs) == 2

    def test_list_runs_filter_by_suite(self, store):
        store.save_run(_make_run("run-1"))
        r2 = _make_run("run-2")
        r2.suite = "other-suite"
        store.save_run(r2)
        runs = store.list_runs(suite="my-suite")
        assert len(runs) == 1
        assert runs[0].id == "run-1"

    def test_multiple_results_per_run(self, store):
        results = [
            _make_result(case_name="case-1", passed=True, score=1.0),
            _make_result(case_name="case-2", passed=False, score=0.0),
        ]
        store.save_run(_make_run("run-1", results=results))
        loaded = store.get_run("run-1")
        assert len(loaded.results) == 2
        names = {r.case_name for r in loaded.results}
        assert names == {"case-1", "case-2"}

    def test_null_cost(self, store):
        store.save_run(_make_run("run-1", results=[_make_result(cost_usd=None)]))
        loaded = store.get_run("run-1")
        assert loaded.results[0].cost_usd is None

    def test_schema_created_automatically(self, tmp_path):
        db_path = tmp_path / "auto.db"
        assert not db_path.exists()
        s = ResultStore(db_path)
        s.save_run(_make_run())
        assert db_path.exists()
        s.close()

    def test_config_and_summary_roundtrip(self, store):
        store.save_run(_make_run())
        loaded = store.get_run("run-1")
        assert loaded.config == {"key": "val"}
        assert loaded.summary == {"total": 1, "passed": 1}

    def test_context_manager(self, tmp_path):
        with ResultStore(tmp_path / "ctx.db") as s:
            s.save_run(_make_run())
            loaded = s.get_run("run-1")
            assert loaded is not None
        # Connection closed after exiting context
        assert s._conn is None

    def test_duplicate_run_id_raises(self, store):
        store.save_run(_make_run("run-1"))
        with pytest.raises(Exception):
            store.save_run(_make_run("run-1"))

    def test_details_and_tools_roundtrip(self, store):
        r = _make_result(
            details={"key": [1, 2, 3]},
            tools_called=[{"name": "search", "args": {"q": "test"}}],
        )
        store.save_run(_make_run("run-1", results=[r]))
        loaded = store.get_run("run-1")
        assert loaded.results[0].details == {"key": [1, 2, 3]}
        assert loaded.results[0].tools_called == [{"name": "search", "args": {"q": "test"}}]
