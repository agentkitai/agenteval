"""Tests for all graders."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from agenteval.graders import get_grader
from agenteval.graders.exact import ExactGrader
from agenteval.graders.contains import ContainsGrader
from agenteval.graders.regex import RegexGrader
from agenteval.graders.tool_check import ToolCheckGrader
from agenteval.graders.llm_judge import LLMJudgeGrader
from agenteval.graders.custom import CustomGrader
from agenteval.models import EvalCase, AgentResult


def _case(expected: dict, grader: str = "exact") -> EvalCase:
    return EvalCase(name="test", input="test input", expected=expected, grader=grader)


def _result(output: str = "", tools: list | None = None) -> AgentResult:
    return AgentResult(output=output, tools_called=tools or [])


# ── ExactGrader ──


@pytest.mark.asyncio
async def test_exact_pass():
    g = ExactGrader()
    r = await g.grade(_case({"output": "hello"}), _result("hello"))
    assert r.passed and r.score == 1.0


@pytest.mark.asyncio
async def test_exact_fail():
    g = ExactGrader()
    r = await g.grade(_case({"output": "hello"}), _result("world"))
    assert not r.passed and r.score == 0.0


@pytest.mark.asyncio
async def test_exact_ignore_case():
    g = ExactGrader(ignore_case=True)
    r = await g.grade(_case({"output": "Hello"}), _result("hello"))
    assert r.passed and r.score == 1.0


# ── ContainsGrader ──


@pytest.mark.asyncio
async def test_contains_all_found():
    g = ContainsGrader()
    r = await g.grade(
        _case({"output_contains": ["foo", "bar"]}),
        _result("foo bar baz"),
    )
    assert r.passed and r.score == 1.0


@pytest.mark.asyncio
async def test_contains_partial():
    g = ContainsGrader()
    r = await g.grade(
        _case({"output_contains": ["foo", "bar", "qux"]}),
        _result("foo baz"),
    )
    assert not r.passed
    assert abs(r.score - 1 / 3) < 0.01


@pytest.mark.asyncio
async def test_contains_none_found():
    g = ContainsGrader()
    r = await g.grade(
        _case({"output_contains": ["x", "y"]}),
        _result("nothing"),
    )
    assert not r.passed and r.score == 0.0


# ── RegexGrader ──


@pytest.mark.asyncio
async def test_regex_match():
    g = RegexGrader()
    r = await g.grade(_case({"pattern": r"\d{3}"}), _result("abc123"))
    assert r.passed and r.score == 1.0


@pytest.mark.asyncio
async def test_regex_no_match():
    g = RegexGrader()
    r = await g.grade(_case({"pattern": r"^\d+$"}), _result("abc"))
    assert not r.passed and r.score == 0.0


@pytest.mark.asyncio
async def test_regex_with_flags():
    g = RegexGrader(flags=["IGNORECASE"])
    r = await g.grade(_case({"pattern": "hello"}), _result("HELLO WORLD"))
    assert r.passed


# ── ToolCheckGrader ──


@pytest.mark.asyncio
async def test_tool_check_unordered():
    g = ToolCheckGrader()
    r = await g.grade(
        _case({"tools_called": ["a", "b"]}),
        _result(tools=[{"name": "b"}, {"name": "a"}]),
    )
    assert r.passed and r.score == 1.0


@pytest.mark.asyncio
async def test_tool_check_ordered():
    g = ToolCheckGrader(ordered=True)
    r = await g.grade(
        _case({"tools_called": ["a", "b"]}),
        _result(tools=[{"name": "a"}, {"name": "b"}]),
    )
    assert r.passed


@pytest.mark.asyncio
async def test_tool_check_ordered_wrong_order():
    g = ToolCheckGrader(ordered=True)
    r = await g.grade(
        _case({"tools_called": ["a", "b"]}),
        _result(tools=[{"name": "b"}, {"name": "a"}]),
    )
    assert not r.passed


@pytest.mark.asyncio
async def test_tool_check_partial():
    g = ToolCheckGrader()
    r = await g.grade(
        _case({"tools_called": ["a", "b", "c"]}),
        _result(tools=[{"name": "a"}]),
    )
    assert not r.passed
    assert abs(r.score - 1 / 3) < 0.01


@pytest.mark.asyncio
async def test_tool_check_missing():
    g = ToolCheckGrader()
    r = await g.grade(
        _case({"tools_called": ["x"]}),
        _result(tools=[]),
    )
    assert not r.passed and r.score == 0.0


# ── LLMJudgeGrader ──


@pytest.mark.asyncio
async def test_llm_judge_pass():
    llm_response = json.dumps({"passed": True, "score": 0.9, "reason": "Good"})
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": llm_response}}]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("agenteval.graders.llm_judge.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        g = LLMJudgeGrader(api_key="test-key")
        r = await g.grade(_case({"behavior": "be polite"}), _result("Thank you!"))
        assert r.passed and r.score == 0.9


@pytest.mark.asyncio
async def test_llm_judge_fail():
    llm_response = json.dumps({"passed": False, "score": 0.2, "reason": "Rude"})
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": llm_response}}]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("agenteval.graders.llm_judge.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        g = LLMJudgeGrader(api_key="test-key")
        r = await g.grade(_case({"behavior": "be polite"}), _result("Go away!"))
        assert not r.passed and r.score == 0.2


# ── CustomGrader ──


@pytest.mark.asyncio
async def test_custom_grader():
    g = CustomGrader(function="tests.helpers.custom_grader_fn:my_grader")
    case = _case({"output": "yes"})
    result = _result("yes")
    r = await g.grade(case, result)
    assert r.passed


@pytest.mark.asyncio
async def test_custom_grader_no_function():
    g = CustomGrader()
    r = await g.grade(_case({}), _result("x"))
    assert not r.passed


# ── Registry ──


def test_get_grader_exact():
    g = get_grader("exact", {})
    assert isinstance(g, ExactGrader)


def test_get_grader_unknown():
    with pytest.raises(ValueError, match="Unknown grader"):
        get_grader("nonexistent", {})
