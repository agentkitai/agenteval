"""Tests for GitHub client, comment formatting, badge generation, and CLI commands."""

from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

import pytest

from agenteval.badge import generate_badge
from agenteval.ci import CIResult
from agenteval.formatters.github_comment import MARKER, format_github_comment
from agenteval.github import GitHubClient
from agenteval.models import EvalResult, EvalRun


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(results=None):
    if results is None:
        results = [
            EvalResult("case-a", True, 0.95, {}, "out", [], 10, 20, 0.001, 150),
            EvalResult("case-b", False, 0.3, {"reason": "wrong"}, "out", [], 5, 10, None, 300),
        ]
    return EvalRun(
        id="run-1", suite="test-suite", agent_ref="m:f",
        config={}, results=results,
        summary={"total": len(results), "passed": sum(r.passed for r in results),
                 "failed": sum(not r.passed for r in results),
                 "pass_rate": sum(r.passed for r in results) / max(len(results), 1)},
        created_at="2026-01-01T00:00:00",
    )


def _make_ci_result(passed=True, pass_rate=0.5, regressions=None):
    regs = regressions or []
    return CIResult(
        passed=passed, pass_rate=pass_rate,
        regression_count=len(regs), regression_pct=0.0,
        regressions=regs, summary="",
    )


def _mock_urlopen(response_data, status=200):
    """Return a context-manager mock for urllib.request.urlopen."""
    resp = mock.MagicMock()
    resp.read.return_value = json.dumps(response_data).encode()
    resp.__enter__ = mock.MagicMock(return_value=resp)
    resp.__exit__ = mock.MagicMock(return_value=False)
    return mock.patch("agenteval.github.urllib.request.urlopen", return_value=resp)


# ---------------------------------------------------------------------------
# B5-S1: GitHubClient tests
# ---------------------------------------------------------------------------

class TestGitHubClient:
    def test_post_comment(self):
        client = GitHubClient("tok", "owner/repo", 42)
        with _mock_urlopen({"id": 1, "body": "hello"}) as m:
            result = client.post_comment("hello")
            assert result["id"] == 1
            req = m.call_args[0][0]
            assert req.get_method() == "POST"
            assert "/repos/owner/repo/issues/42/comments" in req.full_url

    def test_update_comment(self):
        client = GitHubClient("tok", "owner/repo", 42)
        with _mock_urlopen({"id": 99, "body": "updated"}) as m:
            result = client.update_comment(99, "updated")
            assert result["body"] == "updated"
            req = m.call_args[0][0]
            assert req.get_method() == "PATCH"
            assert "/issues/comments/99" in req.full_url

    def test_find_comment_found(self):
        client = GitHubClient("tok", "owner/repo", 1)
        comments = [{"id": 10, "body": "unrelated"}, {"id": 20, "body": "has <!-- marker --> here"}]
        with _mock_urlopen(comments):
            assert client.find_comment("<!-- marker -->") == 20

    def test_find_comment_not_found(self):
        client = GitHubClient("tok", "owner/repo", 1)
        with _mock_urlopen([{"id": 10, "body": "nope"}]):
            assert client.find_comment("<!-- marker -->") is None

    def test_4xx_raises_value_error(self):
        import urllib.error
        client = GitHubClient("tok", "owner/repo", 1)
        err = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        with mock.patch("agenteval.github.urllib.request.urlopen", side_effect=err):
            with pytest.raises(ValueError, match="404"):
                client.post_comment("hi")

    def test_5xx_raises_runtime_error(self):
        import urllib.error
        client = GitHubClient("tok", "owner/repo", 1)
        err = urllib.error.HTTPError("url", 500, "Server Error", {}, None)
        with mock.patch("agenteval.github.urllib.request.urlopen", side_effect=err):
            with pytest.raises(RuntimeError, match="500"):
                client.post_comment("hi")


# ---------------------------------------------------------------------------
# B5-S2: Comment formatting tests
# ---------------------------------------------------------------------------

class TestFormatGitHubComment:
    def test_contains_marker(self):
        text = format_github_comment(_make_ci_result(), _make_run())
        assert MARKER in text

    def test_header_present(self):
        text = format_github_comment(_make_ci_result(), _make_run())
        assert "## 🧪 AgentEval Results" in text

    def test_pass_badge(self):
        text = format_github_comment(_make_ci_result(passed=True), _make_run())
        assert "✅" in text

    def test_fail_badge(self):
        text = format_github_comment(_make_ci_result(passed=False), _make_run())
        assert "❌" in text

    def test_table_rows(self):
        text = format_github_comment(_make_ci_result(), _make_run())
        assert "case-a" in text
        assert "case-b" in text
        assert "✓" in text
        assert "✗" in text

    def test_regressions_section(self):
        text = format_github_comment(
            _make_ci_result(regressions=["case-b"]), _make_run()
        )
        assert "### ⚠️ Regressions" in text
        assert "**case-b**" in text


# ---------------------------------------------------------------------------
# B5-S3: post_or_update_comment tests
# ---------------------------------------------------------------------------

class TestPostOrUpdateComment:
    def test_creates_new_when_no_existing(self):
        client = GitHubClient("tok", "owner/repo", 1)
        with mock.patch.object(client, "find_comment", return_value=None) as fc, \
             mock.patch.object(client, "post_comment", return_value={"id": 1}) as pc:
            result = client.post_or_update_comment("body")
            fc.assert_called_once()
            pc.assert_called_once_with("body")
            assert result["id"] == 1

    def test_updates_existing(self):
        client = GitHubClient("tok", "owner/repo", 1)
        with mock.patch.object(client, "find_comment", return_value=55) as fc, \
             mock.patch.object(client, "update_comment", return_value={"id": 55}) as uc:
            result = client.post_or_update_comment("body")
            fc.assert_called_once()
            uc.assert_called_once_with(55, "body")
            assert result["id"] == 55

    def test_uses_custom_marker(self):
        client = GitHubClient("tok", "owner/repo", 1)
        with mock.patch.object(client, "find_comment", return_value=None) as fc, \
             mock.patch.object(client, "post_comment", return_value={}):
            client.post_or_update_comment("body", marker="<!-- custom -->")
            fc.assert_called_once_with("<!-- custom -->")


# ---------------------------------------------------------------------------
# B5-S4: Badge tests
# ---------------------------------------------------------------------------

class TestBadge:
    def test_green_badge(self):
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            path = f.name
        try:
            generate_badge(0.95, path)
            svg = open(path).read()
            assert "#4c1" in svg
            assert "95%" in svg
            assert "agenteval" in svg
        finally:
            os.unlink(path)

    def test_yellow_badge(self):
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            path = f.name
        try:
            generate_badge(0.75, path)
            svg = open(path).read()
            assert "#dfb317" in svg
        finally:
            os.unlink(path)

    def test_red_badge(self):
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            path = f.name
        try:
            generate_badge(0.5, path)
            svg = open(path).read()
            assert "#e05d44" in svg
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# B5-S5: CLI command tests
# ---------------------------------------------------------------------------

class TestCLIGitHubComment:
    def test_dry_run(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        run = _make_run()
        ci_result = _make_ci_result()

        with mock.patch("agenteval.cli.ResultStore") as MockStore:
            instance = MockStore.return_value
            instance.get_run.return_value = run
            instance.close = mock.MagicMock()

            with mock.patch("agenteval.ci.check_thresholds", return_value=ci_result):
                result = runner.invoke(cli, ["github-comment", "--run", "run-1", "--dry-run", "--db", "test.db"])
                assert result.exit_code == 0
                assert "AgentEval Results" in result.output

    def test_badge_command(self):
        from click.testing import CliRunner
        from agenteval.cli import cli

        runner = CliRunner()
        run = _make_run()
        ci_result = _make_ci_result(pass_rate=0.9)

        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            path = f.name
        try:
            with mock.patch("agenteval.cli.ResultStore") as MockStore:
                instance = MockStore.return_value
                instance.get_run.return_value = run
                instance.close = mock.MagicMock()
                with mock.patch("agenteval.ci.check_thresholds", return_value=ci_result):
                    result = runner.invoke(cli, ["badge", "--run", "run-1", "--output", path, "--db", "test.db"])
                    assert result.exit_code == 0
                    svg = open(path).read()
                    assert "agenteval" in svg
        finally:
            os.unlink(path)
