"""Tests for baseline storage and regression detection."""

from __future__ import annotations

import os
import tempfile

import pytest

from agenteval.baselines import (
    BaselineStore,
    check_regression,
    should_auto_update_baseline,
)
from agenteval.models import EvalResult, EvalRun


def _make_run(suite="test-suite", results=None, run_id="run1"):
    if results is None:
        results = [
            EvalResult(case_name="case1", passed=True, score=1.0, details={},
                       agent_output="ok", tools_called=[], tokens_in=100,
                       tokens_out=50, cost_usd=0.01, latency_ms=100),
            EvalResult(case_name="case2", passed=True, score=0.8, details={},
                       agent_output="ok", tools_called=[], tokens_in=200,
                       tokens_out=100, cost_usd=0.02, latency_ms=200),
        ]
    return EvalRun(
        id=run_id, suite=suite, agent_ref="test:agent", config={},
        results=results,
        summary={
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "pass_rate": sum(1 for r in results if r.passed) / len(results) if results else 0,
            "total_cost_usd": sum(r.cost_usd or 0 for r in results),
            "avg_latency_ms": sum(r.latency_ms for r in results) / len(results) if results else 0,
        },
        created_at="2026-01-01T00:00:00Z",
    )


class TestBaselineStore:
    def test_save_and_get(self, tmp_path):
        db_path = tmp_path / "baselines.db"
        store = BaselineStore(db_path)
        run = _make_run()
        bid = store.save_baseline(run, branch="main", commit_sha="abc123")
        assert bid == 1

        entry = store.get_baseline(bid)
        assert entry is not None
        assert entry.suite == "test-suite"
        assert entry.branch == "main"
        assert entry.commit_sha == "abc123"
        assert len(entry.results) == 2
        assert entry.metrics["pass_rate"] == 1.0
        store.close()

    def test_get_latest_baseline(self, tmp_path):
        db_path = tmp_path / "baselines.db"
        store = BaselineStore(db_path)
        run1 = _make_run(run_id="r1")
        run2 = _make_run(run_id="r2")
        store.save_baseline(run1, branch="main")
        store.save_baseline(run2, branch="main")

        latest = store.get_latest_baseline("test-suite")
        assert latest is not None
        assert latest.id == 2
        store.close()

    def test_get_latest_by_branch(self, tmp_path):
        db_path = tmp_path / "baselines.db"
        store = BaselineStore(db_path)
        run1 = _make_run(run_id="r1")
        run2 = _make_run(run_id="r2")
        store.save_baseline(run1, branch="main")
        store.save_baseline(run2, branch="feature")

        latest = store.get_latest_baseline("test-suite", branch="main")
        assert latest is not None
        assert latest.branch == "main"
        store.close()

    def test_list_baselines(self, tmp_path):
        db_path = tmp_path / "baselines.db"
        store = BaselineStore(db_path)
        store.save_baseline(_make_run(run_id="r1"))
        store.save_baseline(_make_run(run_id="r2"))
        store.save_baseline(_make_run(suite="other", run_id="r3"))

        all_entries = store.list_baselines()
        assert len(all_entries) == 3

        suite_entries = store.list_baselines(suite="test-suite")
        assert len(suite_entries) == 2
        store.close()

    def test_nonexistent_baseline(self, tmp_path):
        db_path = tmp_path / "baselines.db"
        store = BaselineStore(db_path)
        assert store.get_baseline(999) is None
        assert store.get_latest_baseline("nonexistent") is None
        store.close()

    def test_context_manager(self, tmp_path):
        db_path = tmp_path / "baselines.db"
        with BaselineStore(db_path) as store:
            store.save_baseline(_make_run())


class TestCheckRegression:
    def test_no_regression(self, tmp_path):
        db_path = tmp_path / "baselines.db"
        store = BaselineStore(db_path)
        run = _make_run()
        bid = store.save_baseline(run)
        baseline = store.get_baseline(bid)

        result = check_regression(run, baseline, threshold=0.05)
        assert result.passed is True
        assert len(result.regressions) == 0
        store.close()

    def test_regression_detected(self, tmp_path):
        db_path = tmp_path / "baselines.db"
        store = BaselineStore(db_path)
        run1 = _make_run(run_id="r1")
        bid = store.save_baseline(run1)
        baseline = store.get_baseline(bid)

        # Create run with lower scores
        results = [
            EvalResult(case_name="case1", passed=False, score=0.3, details={},
                       agent_output="bad", tools_called=[], tokens_in=100,
                       tokens_out=50, cost_usd=0.01, latency_ms=100),
            EvalResult(case_name="case2", passed=True, score=0.8, details={},
                       agent_output="ok", tools_called=[], tokens_in=200,
                       tokens_out=100, cost_usd=0.02, latency_ms=200),
        ]
        run2 = _make_run(run_id="r2", results=results)

        result = check_regression(run2, baseline, threshold=0.05)
        assert result.passed is False
        assert len(result.regressions) == 1
        assert result.regressions[0]["case_name"] == "case1"
        store.close()

    def test_new_case_not_regression(self, tmp_path):
        db_path = tmp_path / "baselines.db"
        store = BaselineStore(db_path)
        run1 = _make_run(run_id="r1")
        bid = store.save_baseline(run1)
        baseline = store.get_baseline(bid)

        results = [
            EvalResult(case_name="case1", passed=True, score=1.0, details={},
                       agent_output="ok", tools_called=[], tokens_in=100,
                       tokens_out=50, cost_usd=0.01, latency_ms=100),
            EvalResult(case_name="case3", passed=False, score=0.0, details={},
                       agent_output="bad", tools_called=[], tokens_in=100,
                       tokens_out=50, cost_usd=0.01, latency_ms=100),
        ]
        run2 = _make_run(run_id="r2", results=results)

        result = check_regression(run2, baseline, threshold=0.05)
        assert result.passed is True
        store.close()

    def test_per_metric_threshold(self, tmp_path):
        db_path = tmp_path / "baselines.db"
        store = BaselineStore(db_path)
        run1 = _make_run(run_id="r1")
        bid = store.save_baseline(run1)
        baseline = store.get_baseline(bid)

        results = [
            EvalResult(case_name="case1", passed=True, score=0.9, details={},
                       agent_output="ok", tools_called=[], tokens_in=100,
                       tokens_out=50, cost_usd=0.01, latency_ms=100),
            EvalResult(case_name="case2", passed=True, score=0.7, details={},
                       agent_output="ok", tools_called=[], tokens_in=200,
                       tokens_out=100, cost_usd=0.02, latency_ms=200),
        ]
        run2 = _make_run(run_id="r2", results=results)

        # case1: drop=0.1, threshold=0.2 → ok; case2: drop=0.1, threshold=0.05 → regression
        result = check_regression(run2, baseline, threshold=0.05,
                                  per_metric_thresholds={"case1": 0.2})
        assert result.passed is False
        assert len(result.regressions) == 1
        assert result.regressions[0]["case_name"] == "case2"
        store.close()


class TestAutoUpdateBaseline:
    def test_disabled(self):
        assert should_auto_update_baseline(auto_baseline=False) is False

    def test_github_main(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REF_NAME", "main")
        assert should_auto_update_baseline(auto_baseline=True) is True

    def test_github_feature_branch(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REF_NAME", "feature-x")
        # Clear other env vars
        monkeypatch.delenv("CI_COMMIT_BRANCH", raising=False)
        monkeypatch.delenv("BRANCH_NAME", raising=False)
        monkeypatch.delenv("CI_BRANCH", raising=False)
        assert should_auto_update_baseline(auto_baseline=True) is False

    def test_gitlab_main(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
        monkeypatch.setenv("CI_COMMIT_BRANCH", "main")
        assert should_auto_update_baseline(auto_baseline=True) is True

    def test_custom_default_branch(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REF_NAME", "develop")
        assert should_auto_update_baseline(auto_baseline=True, default_branch="develop") is True
