"""Tests for agenteval.generators — TG-1 and TG-2."""

from __future__ import annotations

import os
import tempfile

import yaml
import pytest

from agenteval.models import EvalCase, EvalSuite


# ── TG-1: MutationStrategy base + 7 strategies ──────────────────────────


class TestMutationStrategyRegistry:
    def test_get_strategy_returns_instance(self):
        from agenteval.generators import get_strategy
        s = get_strategy("empty")
        assert hasattr(s, "mutate")

    def test_get_strategy_unknown_raises(self):
        from agenteval.generators import get_strategy
        with pytest.raises(ValueError, match="Unknown"):
            get_strategy("nonexistent")

    def test_all_seven_registered(self):
        from agenteval.generators import get_strategy
        names = ["empty", "max_length", "unicode", "sql_injection",
                 "prompt_injection", "typo", "negation"]
        for n in names:
            assert get_strategy(n) is not None


class TestEmptyStrategy:
    def test_returns_empty_string(self):
        from agenteval.generators import get_strategy
        assert get_strategy("empty").mutate("hello") == [""]


class TestMaxLengthStrategy:
    def test_returns_repeated_input(self):
        from agenteval.generators import get_strategy
        result = get_strategy("max_length").mutate("ab")
        assert result == ["ab" * 100]


class TestUnicodeStrategy:
    def test_returns_three_variants(self):
        from agenteval.generators import get_strategy
        result = get_strategy("unicode").mutate("hello")
        assert len(result) == 3
        # Each should contain original text somewhere
        for r in result:
            assert "hello" in r or len(r) > 0


class TestSqlInjectionStrategy:
    def test_returns_mutations(self):
        from agenteval.generators import get_strategy
        result = get_strategy("sql_injection").mutate("test")
        assert len(result) >= 1
        assert any("'" in r or "OR" in r or "--" in r for r in result)


class TestPromptInjectionStrategy:
    def test_returns_mutations(self):
        from agenteval.generators import get_strategy
        result = get_strategy("prompt_injection").mutate("test")
        assert len(result) >= 1
        assert any("ignore" in r.lower() for r in result)


class TestTypoStrategy:
    def test_deterministic(self):
        from agenteval.generators import get_strategy
        s = get_strategy("typo")
        r1 = s.mutate("hello world")
        r2 = s.mutate("hello world")
        assert r1 == r2

    def test_returns_mutations(self):
        from agenteval.generators import get_strategy
        result = get_strategy("typo").mutate("hello world")
        assert len(result) >= 1


class TestNegationStrategy:
    def test_inserts_negation(self):
        from agenteval.generators import get_strategy
        result = get_strategy("negation").mutate("I like cats")
        assert len(result) >= 1
        assert any("not" in r.lower() or "don't" in r.lower() for r in result)


class TestGenerateOrchestrator:
    def test_generate_produces_valid_cases(self):
        from agenteval.generators import generate
        suite = EvalSuite(
            name="test", agent="mock:fn",
            cases=[EvalCase(name="c1", input="hi", expected={"output": "hello"},
                            grader="exact", tags=["original"])],
        )
        result = generate(suite)
        assert isinstance(result, EvalSuite)
        # Should have original + mutations
        assert len(result.cases) > 1
        # Original preserved
        assert result.cases[0].name == "c1"
        # Generated cases tagged
        gen_cases = [c for c in result.cases if any(t.startswith("generated:") for t in c.tags)]
        assert len(gen_cases) > 0

    def test_generate_with_strategy_filter(self):
        from agenteval.generators import generate
        suite = EvalSuite(
            name="test", agent="mock:fn",
            cases=[EvalCase(name="c1", input="hi", expected={"output": "hello"},
                            grader="exact")],
        )
        result = generate(suite, strategies=["empty"])
        gen = [c for c in result.cases if c.name != "c1"]
        assert all(any("generated:empty" in t for t in c.tags) for c in gen)

    def test_generate_count_limits(self):
        from agenteval.generators import generate
        suite = EvalSuite(
            name="test", agent="mock:fn",
            cases=[EvalCase(name="c1", input="hello world test",
                            expected={"output": "x"}, grader="exact")],
        )
        result = generate(suite, strategies=["unicode"], count=1)
        gen = [c for c in result.cases if c.name != "c1"]
        # unicode normally produces 3, but count=1 should limit to 1
        assert len(gen) == 1


# ── TG-2: Generate CLI command + YAML output ────────────────────────────


class TestGenerateCLI:
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

    def test_generate_command_exists(self):
        from agenteval.cli import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "--help"])
        assert result.exit_code == 0
        assert "generate" in result.output.lower() or "--suite" in result.output

    def test_generate_produces_yaml(self, tmp_path):
        from agenteval.cli import cli
        from click.testing import CliRunner
        suite_file = self._make_suite_file(tmp_path)
        out_file = str(tmp_path / "expanded.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "--suite", suite_file, "--output", out_file])
        assert result.exit_code == 0, result.output
        assert os.path.exists(out_file)
        with open(out_file) as f:
            data = yaml.safe_load(f)
        assert len(data["cases"]) > 1

    def test_generate_output_loadable(self, tmp_path):
        from agenteval.cli import cli
        from agenteval.loader import load_suite
        from click.testing import CliRunner
        suite_file = self._make_suite_file(tmp_path)
        out_file = str(tmp_path / "expanded.yaml")
        runner = CliRunner()
        runner.invoke(cli, ["generate", "--suite", suite_file, "--output", out_file])
        loaded = load_suite(out_file)
        assert len(loaded.cases) > 1

    def test_generate_strategies_filter(self, tmp_path):
        from agenteval.cli import cli
        from click.testing import CliRunner
        suite_file = self._make_suite_file(tmp_path)
        out_file = str(tmp_path / "expanded.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "--suite", suite_file, "--output", out_file,
                                     "--strategies", "empty,negation"])
        assert result.exit_code == 0
        with open(out_file) as f:
            data = yaml.safe_load(f)
        tags = [t for c in data["cases"] for t in c.get("tags", [])]
        gen_tags = [t for t in tags if t.startswith("generated:")]
        strategies_used = {t.split(":")[1] for t in gen_tags}
        assert strategies_used <= {"empty", "negation"}

    def test_generate_count_option(self, tmp_path):
        from agenteval.cli import cli
        from click.testing import CliRunner
        suite_file = self._make_suite_file(tmp_path)
        out_file = str(tmp_path / "expanded.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "--suite", suite_file, "--output", out_file,
                                     "--strategies", "unicode", "--count", "1"])
        assert result.exit_code == 0
        with open(out_file) as f:
            data = yaml.safe_load(f)
        # 1 original + 1 mutation
        assert len(data["cases"]) == 2

    def test_generate_missing_suite_errors(self):
        from agenteval.cli import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "--suite", "/nonexistent.yaml", "--output", "/tmp/x.yaml"])
        assert result.exit_code != 0
