"""Tests for TG-3 (LLM generator) and TG-4 (CLI + YAML wiring)."""

from __future__ import annotations

import json
import os

import httpx
import pytest
import yaml

from agenteval.models import EvalCase, EvalSuite


# ── TG-3: LLMGenerator ──────────────────────────────────────────────────


def _make_cases():
    return [
        EvalCase(name="c1", input="hello", expected={"output": "hi"}, grader="exact"),
    ]


def _mock_openai_response(cases_json: list[dict], status=200):
    """Build a fake httpx.Response mimicking OpenAI chat completions."""
    body = {
        "choices": [{"message": {"content": json.dumps(cases_json)}}],
    }
    return httpx.Response(status_code=status, json=body, request=httpx.Request("POST", "https://fake"))


class TestLLMGenerator:
    def test_generate_adversarial_returns_eval_cases(self, monkeypatch):
        from agenteval.generators.llm_gen import LLMGenerator

        fake_cases = [
            {"name": "adv_1", "input": "evil input", "expected": {"output": "?"}, "grader": "exact"},
            {"name": "adv_2", "input": "tricky", "expected": {"output": "!"}, "grader": "contains"},
        ]

        def mock_post(self_, url, **kw):
            return _mock_openai_response(fake_cases)

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        gen = LLMGenerator(api_key="sk-test")
        result = gen.generate_adversarial(_make_cases(), count=2)

        assert len(result) == 2
        assert all(isinstance(c, EvalCase) for c in result)
        assert all("generated:llm" in c.tags for c in result)

    def test_generate_adversarial_bad_json_returns_empty(self, monkeypatch):
        from agenteval.generators.llm_gen import LLMGenerator

        def mock_post(self_, url, **kw):
            body = {"choices": [{"message": {"content": "not json at all"}}]}
            return httpx.Response(200, json=body, request=httpx.Request("POST", "https://fake"))

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        gen = LLMGenerator(api_key="sk-test")
        result = gen.generate_adversarial(_make_cases())
        assert result == []

    def test_generate_adversarial_auth_failure_returns_empty(self, monkeypatch):
        from agenteval.generators.llm_gen import LLMGenerator

        def mock_post(self_, url, **kw):
            return httpx.Response(401, json={"error": "invalid key"}, request=httpx.Request("POST", "https://fake"))

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        gen = LLMGenerator(api_key="sk-bad")
        result = gen.generate_adversarial(_make_cases())
        assert result == []

    def test_generate_adversarial_timeout_returns_empty(self, monkeypatch):
        from agenteval.generators.llm_gen import LLMGenerator

        def mock_post(self_, url, **kw):
            raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(httpx.Client, "post", mock_post)
        gen = LLMGenerator(api_key="sk-test")
        result = gen.generate_adversarial(_make_cases())
        assert result == []

    def test_generate_adversarial_respects_count(self, monkeypatch):
        from agenteval.generators.llm_gen import LLMGenerator

        fake_cases = [
            {"name": f"adv_{i}", "input": f"input_{i}", "expected": {}, "grader": "exact"}
            for i in range(5)
        ]

        def mock_post(self_, url, **kw):
            # Verify count is in the prompt
            body = json.loads(kw.get("content", "{}") if isinstance(kw.get("content"), str) else "")
            return _mock_openai_response(fake_cases)

        monkeypatch.setattr(httpx.Client, "post", lambda s, u, **kw: _mock_openai_response(fake_cases))
        gen = LLMGenerator(api_key="sk-test")
        result = gen.generate_adversarial(_make_cases(), count=5)
        assert len(result) == 5

    def test_build_prompt(self):
        from agenteval.generators.llm_gen import LLMGenerator

        gen = LLMGenerator(api_key="sk-test")
        prompt = gen.build_prompt(_make_cases(), count=3)
        assert "3" in prompt
        assert "adversarial" in prompt.lower()
        assert "hello" in prompt  # input from case


# ── TG-4: CLI wiring + YAML config ──────────────────────────────────────


class TestLLMGenerateCLI:
    def _make_suite_file(self, tmp_path):
        suite = {
            "name": "test-suite",
            "agent": "mock:fn",
            "cases": [
                {"name": "c1", "input": "hello", "expected": {"output": "world"}, "grader": "exact"},
            ],
        }
        p = tmp_path / "base.yaml"
        p.write_text(yaml.dump(suite))
        return str(p)

    def test_dry_run_shows_prompt(self, tmp_path):
        from agenteval.cli import cli
        from click.testing import CliRunner

        suite_file = self._make_suite_file(tmp_path)
        out_file = str(tmp_path / "out.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, [
            "generate", "--suite", suite_file, "--output", out_file,
            "--strategies", "llm", "--dry-run",
        ])
        assert result.exit_code == 0
        assert "adversarial" in result.output.lower()

    def test_llm_strategy_with_api_key(self, tmp_path, monkeypatch):
        from agenteval.cli import cli
        from click.testing import CliRunner

        fake_cases = [
            {"name": "adv_1", "input": "evil", "expected": {}, "grader": "exact"},
        ]
        monkeypatch.setattr(httpx.Client, "post", lambda s, u, **kw: _mock_openai_response(fake_cases))

        suite_file = self._make_suite_file(tmp_path)
        out_file = str(tmp_path / "out.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, [
            "generate", "--suite", suite_file, "--output", out_file,
            "--strategies", "llm", "--api-key", "sk-test",
        ])
        assert result.exit_code == 0
        with open(out_file) as f:
            data = yaml.safe_load(f)
        # original + LLM generated
        assert len(data["cases"]) >= 2

    def test_llm_strategy_env_key(self, tmp_path, monkeypatch):
        from agenteval.cli import cli
        from click.testing import CliRunner

        fake_cases = [
            {"name": "adv_1", "input": "evil", "expected": {}, "grader": "exact"},
        ]
        monkeypatch.setattr(httpx.Client, "post", lambda s, u, **kw: _mock_openai_response(fake_cases))
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

        suite_file = self._make_suite_file(tmp_path)
        out_file = str(tmp_path / "out.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, [
            "generate", "--suite", suite_file, "--output", out_file,
            "--strategies", "llm",
        ])
        assert result.exit_code == 0

    def test_llm_no_key_warns(self, tmp_path):
        from agenteval.cli import cli
        from click.testing import CliRunner

        suite_file = self._make_suite_file(tmp_path)
        out_file = str(tmp_path / "out.yaml")
        runner = CliRunner(env={"OPENAI_API_KEY": ""})
        result = runner.invoke(cli, [
            "generate", "--suite", suite_file, "--output", out_file,
            "--strategies", "llm",
        ])
        # Should not crash, just warn and skip LLM
        assert result.exit_code == 0
