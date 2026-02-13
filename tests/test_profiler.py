"""Tests for the performance profiler module."""

from __future__ import annotations

import json
import math

import pytest

from agenteval.models import EvalResult, EvalRun
from agenteval.profiler import (
    ProfileResult,
    Profiler,
    SuiteProfile,
    TrendResult,
    generate_recommendations,
    trend_analysis,
)


def _make_result(name: str, latency_ms: int = 100, cost_usd: float = 0.01,
                 passed: bool = True, score: float = 1.0) -> EvalResult:
    return EvalResult(
        case_name=name, passed=passed, score=score, details={},
        agent_output="out", tools_called=[], tokens_in=10,
        tokens_out=20, cost_usd=cost_usd, latency_ms=latency_ms,
    )


def _make_run(run_id: str, results: list[EvalResult], suite: str = "test-suite") -> EvalRun:
    return EvalRun(
        id=run_id, suite=suite, agent_ref="agent:fn",
        config={}, results=results, summary={}, created_at="2026-01-01T00:00:00",
    )


# === PP-1: Profiler core ===

class TestProfilerCore:
    def test_profile_run_basic(self):
        results = [_make_result("a", 100, 0.01), _make_result("b", 200, 0.02)]
        run = _make_run("r1", results)
        profile = Profiler().profile_run(run)
        assert isinstance(profile, SuiteProfile)
        assert len(profile.results) == 2
        assert profile.mean_latency == 150.0
        assert profile.mean_cost == 0.015
        assert profile.total_cost == pytest.approx(0.03)

    def test_profile_result_fields(self):
        results = [_make_result("a", 100, 0.01)]
        run = _make_run("r1", results)
        profile = Profiler().profile_run(run)
        pr = profile.results[0]
        assert pr.case_name == "a"
        assert pr.latency_ms == 100
        assert pr.cost_usd == 0.01

    def test_outlier_detection(self):
        # Many tightly clustered cases + 1 extreme outlier
        results = [_make_result(f"n{i}", 100, 0.01) for i in range(10)]
        results.append(_make_result("outlier", 1000, 0.01))
        run = _make_run("r1", results)
        profile = Profiler().profile_run(run)
        outliers = [r for r in profile.results if r.is_outlier]
        assert len(outliers) >= 1
        assert outliers[0].case_name == "outlier"
        assert profile.outlier_count >= 1

    def test_no_outliers_uniform(self):
        results = [_make_result(f"c{i}", 100, 0.01) for i in range(5)]
        run = _make_run("r1", results)
        profile = Profiler().profile_run(run)
        assert profile.outlier_count == 0

    def test_single_case(self):
        """Single case should not crash (stdev undefined for n=1)."""
        results = [_make_result("solo", 100, 0.05)]
        run = _make_run("r1", results)
        profile = Profiler().profile_run(run)
        assert len(profile.results) == 1
        assert not profile.results[0].is_outlier

    def test_empty_run(self):
        run = _make_run("r1", [])
        profile = Profiler().profile_run(run)
        assert len(profile.results) == 0
        assert profile.mean_latency == 0.0

    def test_z_score_computed(self):
        results = [
            _make_result("a", 100, 0.01),
            _make_result("b", 200, 0.01),
            _make_result("c", 300, 0.01),
        ]
        run = _make_run("r1", results)
        profile = Profiler().profile_run(run)
        # z-scores should be finite
        for r in profile.results:
            assert math.isfinite(r.z_score)

    def test_none_cost_treated_as_zero(self):
        r = _make_result("a", 100, 0.0)
        r.cost_usd = None
        run = _make_run("r1", [r])
        profile = Profiler().profile_run(run)
        assert profile.total_cost == 0.0


# === PP-2: Trend analysis ===

class TestTrendAnalysis:
    def test_improving_trend(self):
        runs = [
            _make_run(f"r{i}", [_make_result("a", 200 - i * 30, 0.01)])
            for i in range(5)
        ]
        result = trend_analysis(runs)
        assert isinstance(result, TrendResult)
        assert result.case_trends["a"] == "improving"

    def test_degrading_trend(self):
        runs = [
            _make_run(f"r{i}", [_make_result("a", 100 + i * 30, 0.01)])
            for i in range(5)
        ]
        result = trend_analysis(runs)
        assert result.case_trends["a"] == "degrading"

    def test_stable_trend(self):
        runs = [
            _make_run(f"r{i}", [_make_result("a", 100 + i, 0.01)])
            for i in range(5)
        ]
        result = trend_analysis(runs)
        assert result.case_trends["a"] == "stable"

    def test_overall_direction(self):
        runs = [
            _make_run(f"r{i}", [_make_result("a", 200 - i * 30, 0.01)])
            for i in range(5)
        ]
        result = trend_analysis(runs)
        assert result.overall_direction in ("improving", "degrading", "stable")

    def test_single_run_stable(self):
        runs = [_make_run("r0", [_make_result("a", 100, 0.01)])]
        result = trend_analysis(runs)
        assert result.case_trends["a"] == "stable"


# === PP-3: Recommendations ===

class TestRecommendations:
    def test_caching_recommendation(self):
        results = [
            _make_result("fast", 100, 0.01),
            _make_result("slow", 400, 0.01),  # >3x avg of 250? No. Need >3x mean
        ]
        # mean = 250, 3x = 750 — need a much slower one
        results = [_make_result(f"n{i}", 100, 0.01) for i in range(10)]
        results.append(_make_result("slow", 1000, 0.01))
        run = _make_run("r1", results)
        profile = Profiler().profile_run(run)
        recs = generate_recommendations(profile)
        assert any("caching" in r.lower() for r in recs)

    def test_cost_hotspot_recommendation(self):
        results = [
            _make_result("cheap", 100, 0.01),
            _make_result("expensive", 100, 0.90),
        ]
        run = _make_run("r1", results)
        profile = Profiler().profile_run(run)
        recs = generate_recommendations(profile)
        assert any("hotspot" in r.lower() for r in recs)

    def test_variability_recommendation(self):
        results = [_make_result(f"n{i}", 100, 0.01) for i in range(10)]
        results.append(_make_result("outlier", 1000, 0.01))
        run = _make_run("r1", results)
        profile = Profiler().profile_run(run)
        recs = generate_recommendations(profile)
        assert any("variability" in r.lower() for r in recs)

    def test_no_recommendations_clean(self):
        results = [_make_result(f"c{i}", 100, 0.01) for i in range(5)]
        run = _make_run("r1", results)
        profile = Profiler().profile_run(run)
        recs = generate_recommendations(profile)
        assert len(recs) == 0


# === PP-4: CLI profile command ===

class TestProfileCLI:
    def test_profile_text_format(self, tmp_path):
        from click.testing import CliRunner
        from agenteval.cli import cli
        from agenteval.store import ResultStore

        db_path = str(tmp_path / "test.db")
        store = ResultStore(db_path)
        results = [
            _make_result("case_a", 100, 0.01),
            _make_result("case_b", 200, 0.02),
        ]
        run = _make_run("run1", results)
        run.summary = {"total": 2, "passed": 2, "failed": 0, "pass_rate": 1.0}
        store.save_run(run)
        store.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["profile", "--run", "run1", "--db", db_path])
        assert result.exit_code == 0
        assert "case_a" in result.output
        assert "case_b" in result.output

    def test_profile_json_format(self, tmp_path):
        from click.testing import CliRunner
        from agenteval.cli import cli
        from agenteval.store import ResultStore

        db_path = str(tmp_path / "test.db")
        store = ResultStore(db_path)
        results = [_make_result("case_a", 100, 0.01)]
        run = _make_run("run1", results)
        run.summary = {"total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0}
        store.save_run(run)
        store.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["profile", "--run", "run1", "--db", db_path, "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "results" in data
        assert "mean_latency" in data

    def test_profile_csv_format(self, tmp_path):
        from click.testing import CliRunner
        from agenteval.cli import cli
        from agenteval.store import ResultStore

        db_path = str(tmp_path / "test.db")
        store = ResultStore(db_path)
        results = [_make_result("case_a", 150, 0.05)]
        run = _make_run("run1", results)
        run.summary = {"total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0}
        store.save_run(run)
        store.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["profile", "--run", "run1", "--db", db_path, "--format", "csv"])
        assert result.exit_code == 0
        assert "case_name" in result.output  # header
        assert "case_a" in result.output
