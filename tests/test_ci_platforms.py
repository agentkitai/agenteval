"""Tests for multi-CI platform support."""

from __future__ import annotations

import os

import pytest

from agenteval.ci_platforms import (
    CIPlatform,
    detect_ci_platform,
    format_circleci_results,
    format_gitlab_comment,
    generate_jenkins_html_report,
)
from agenteval.models import EvalResult, EvalRun


def _make_run(failed=0):
    results = []
    for i in range(3):
        passed = i >= failed
        results.append(EvalResult(
            case_name=f"case{i+1}", passed=passed,
            score=1.0 if passed else 0.0,
            details={"reason": "ok" if passed else "failed"},
            agent_output="ok", tools_called=[], tokens_in=100,
            tokens_out=50, cost_usd=0.01, latency_ms=100,
        ))
    total = len(results)
    p = sum(1 for r in results if r.passed)
    return EvalRun(
        id="run1", suite="test-suite", agent_ref="test:agent", config={},
        results=results,
        summary={"total": total, "passed": p, "failed": total - p,
                 "pass_rate": p / total, "total_cost_usd": 0.03,
                 "avg_latency_ms": 100},
        created_at="2026-01-01T00:00:00Z",
    )


class TestDetectPlatform:
    def test_github(self, monkeypatch):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("GITHUB_REF_NAME", "main")
        monkeypatch.setenv("GITHUB_SHA", "abc123")
        monkeypatch.setenv("GITHUB_REPOSITORY", "user/repo")
        monkeypatch.delenv("GITLAB_CI", raising=False)
        monkeypatch.delenv("CIRCLECI", raising=False)
        monkeypatch.delenv("JENKINS_URL", raising=False)

        env = detect_ci_platform()
        assert env.platform == CIPlatform.GITHUB
        assert env.branch == "main"
        assert env.commit_sha == "abc123"

    def test_gitlab(self, monkeypatch):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.setenv("GITLAB_CI", "true")
        monkeypatch.setenv("CI_COMMIT_BRANCH", "feature")
        monkeypatch.setenv("CI_COMMIT_SHA", "def456")
        monkeypatch.setenv("CI_MERGE_REQUEST_IID", "42")
        monkeypatch.delenv("CIRCLECI", raising=False)
        monkeypatch.delenv("JENKINS_URL", raising=False)

        env = detect_ci_platform()
        assert env.platform == CIPlatform.GITLAB
        assert env.pr_number == 42

    def test_circleci(self, monkeypatch):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)
        monkeypatch.setenv("CIRCLECI", "true")
        monkeypatch.setenv("CIRCLE_BRANCH", "dev")
        monkeypatch.setenv("CIRCLE_SHA1", "ghi789")
        monkeypatch.delenv("JENKINS_URL", raising=False)

        env = detect_ci_platform()
        assert env.platform == CIPlatform.CIRCLECI
        assert env.branch == "dev"

    def test_jenkins(self, monkeypatch):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)
        monkeypatch.delenv("CIRCLECI", raising=False)
        monkeypatch.setenv("JENKINS_URL", "http://jenkins.local")
        monkeypatch.setenv("GIT_BRANCH", "release")

        env = detect_ci_platform()
        assert env.platform == CIPlatform.JENKINS
        assert env.branch == "release"

    def test_unknown(self, monkeypatch):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)
        monkeypatch.delenv("CIRCLECI", raising=False)
        monkeypatch.delenv("JENKINS_URL", raising=False)

        env = detect_ci_platform()
        assert env.platform == CIPlatform.UNKNOWN


class TestGitLabComment:
    def test_passing(self):
        comment = format_gitlab_comment(_make_run(failed=0))
        assert "PASSED" in comment
        assert "test-suite" in comment

    def test_failing(self):
        comment = format_gitlab_comment(_make_run(failed=2))
        assert "FAILED" in comment
        assert "Failed Cases" in comment


class TestCircleCIResults:
    def test_format(self):
        result = format_circleci_results(_make_run(failed=1))
        assert len(result["tests"]) == 3
        assert result["summary"]["failed"] == 1
        # Check a failed test
        failed = [t for t in result["tests"] if t["result"] == "failure"]
        assert len(failed) == 1


class TestJenkinsReport:
    def test_html_structure(self):
        html = generate_jenkins_html_report(_make_run(failed=1))
        assert "<html>" in html
        assert "AgentEval" in html
        assert "FAIL" in html
        assert "case1" in html

    def test_passing_run(self):
        html = generate_jenkins_html_report(_make_run(failed=0))
        assert "PASSED" in html
        assert "#4caf50" in html
