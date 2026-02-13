"""Tests for Batch 1 advanced graders: json_schema, semantic, latency, cost."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from agenteval.graders import get_grader
from agenteval.graders.json_schema import JsonSchemaGrader
from agenteval.graders.semantic import SemanticGrader
from agenteval.graders.latency import LatencyGrader
from agenteval.graders.cost import CostGrader
from agenteval.models import EvalCase, AgentResult


def _case(expected: dict = None, grader: str = "exact") -> EvalCase:
    return EvalCase(name="test", input="test input", expected=expected or {}, grader=grader)


def _result(output: str = "", **kwargs) -> AgentResult:
    return AgentResult(output=output, **kwargs)


# ── JsonSchemaGrader ──

SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}


@pytest.mark.asyncio
async def test_json_schema_valid():
    g = JsonSchemaGrader(schema=SCHEMA)
    r = await g.grade(_case(), _result('{"name": "Alice"}'))
    assert r.passed and r.score == 1.0


@pytest.mark.asyncio
async def test_json_schema_invalid():
    g = JsonSchemaGrader(schema=SCHEMA)
    r = await g.grade(_case(), _result('{"age": 30}'))
    assert not r.passed and r.score == 0.0
    assert "name" in r.reason


@pytest.mark.asyncio
async def test_json_schema_bad_json():
    g = JsonSchemaGrader(schema=SCHEMA)
    r = await g.grade(_case(), _result("not json"))
    assert not r.passed and r.score == 0.0
    assert "Invalid JSON" in r.reason


@pytest.mark.asyncio
async def test_json_schema_from_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(SCHEMA, f)
        f.flush()
        path = f.name
    try:
        g = JsonSchemaGrader(schema_file=path)
        r = await g.grade(_case(), _result('{"name": "Bob"}'))
        assert r.passed
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_json_schema_no_schema():
    g = JsonSchemaGrader()
    with pytest.raises(ValueError, match="requires"):
        await g.grade(_case(), _result("{}"))


@pytest.mark.asyncio
async def test_json_schema_complex():
    schema = {"type": "array", "items": {"type": "integer"}, "minItems": 1}
    g = JsonSchemaGrader(schema=schema)
    r = await g.grade(_case(), _result("[1, 2, 3]"))
    assert r.passed


@pytest.mark.asyncio
async def test_json_schema_complex_fail():
    schema = {"type": "array", "items": {"type": "integer"}, "minItems": 1}
    g = JsonSchemaGrader(schema=schema)
    r = await g.grade(_case(), _result("[]"))
    assert not r.passed


@pytest.mark.asyncio
async def test_json_schema_nested():
    schema = {"type": "object", "properties": {"a": {"type": "object", "properties": {"b": {"type": "number"}}, "required": ["b"]}}, "required": ["a"]}
    g = JsonSchemaGrader(schema=schema)
    r = await g.grade(_case(), _result('{"a": {"b": 42}}'))
    assert r.passed


# ── SemanticGrader ──


def _mock_sentence_transformers(similarity: float):
    """Return a patch context that mocks sentence-transformers with given similarity."""
    mock_model = MagicMock()
    mock_tensor = MagicMock()
    mock_model.encode.return_value = mock_tensor

    mock_cos_result = MagicMock()
    mock_cos_result.item.return_value = similarity

    mock_cos_sim = MagicMock(return_value=mock_cos_result)

    mock_st = MagicMock()
    mock_st.SentenceTransformer.return_value = mock_model
    mock_st.util.cos_sim = mock_cos_sim

    return mock_st, mock_cos_sim


@pytest.mark.asyncio
async def test_semantic_pass():
    mock_st, mock_cos = _mock_sentence_transformers(0.92)
    with patch.dict("sys.modules", {
        "sentence_transformers": mock_st,
        "sentence_transformers.util": mock_st.util,
    }):
        g = SemanticGrader(expected="hello world", threshold=0.8)
        r = await g.grade(_case(), _result("hi world"))
        assert r.passed and abs(r.score - 0.92) < 0.01


@pytest.mark.asyncio
async def test_semantic_fail():
    mock_st, _ = _mock_sentence_transformers(0.3)
    with patch.dict("sys.modules", {
        "sentence_transformers": mock_st,
        "sentence_transformers.util": mock_st.util,
    }):
        g = SemanticGrader(expected="hello", threshold=0.8)
        r = await g.grade(_case(), _result("xyz"))
        assert not r.passed and abs(r.score - 0.3) < 0.01


@pytest.mark.asyncio
async def test_semantic_custom_threshold():
    mock_st, _ = _mock_sentence_transformers(0.5)
    with patch.dict("sys.modules", {
        "sentence_transformers": mock_st,
        "sentence_transformers.util": mock_st.util,
    }):
        g = SemanticGrader(expected="a", threshold=0.4)
        r = await g.grade(_case(), _result("b"))
        assert r.passed


@pytest.mark.asyncio
async def test_semantic_exact_threshold():
    mock_st, _ = _mock_sentence_transformers(0.8)
    with patch.dict("sys.modules", {
        "sentence_transformers": mock_st,
        "sentence_transformers.util": mock_st.util,
    }):
        g = SemanticGrader(expected="a", threshold=0.8)
        r = await g.grade(_case(), _result("a"))
        assert r.passed


@pytest.mark.asyncio
async def test_semantic_import_error():
    with patch.dict("sys.modules", {"sentence_transformers": None}):
        g = SemanticGrader(expected="a")
        with pytest.raises(ImportError, match="agentevalkit\\[semantic\\]"):
            await g.grade(_case(), _result("b"))


@pytest.mark.asyncio
async def test_semantic_score_is_similarity():
    mock_st, _ = _mock_sentence_transformers(0.75)
    with patch.dict("sys.modules", {
        "sentence_transformers": mock_st,
        "sentence_transformers.util": mock_st.util,
    }):
        g = SemanticGrader(expected="a", threshold=0.5)
        r = await g.grade(_case(), _result("b"))
        assert r.score == 0.75


@pytest.mark.asyncio
async def test_semantic_reason_format():
    mock_st, _ = _mock_sentence_transformers(0.85)
    with patch.dict("sys.modules", {
        "sentence_transformers": mock_st,
        "sentence_transformers.util": mock_st.util,
    }):
        g = SemanticGrader(expected="a", threshold=0.8)
        r = await g.grade(_case(), _result("b"))
        assert "0.850" in r.reason and "≥" in r.reason


@pytest.mark.asyncio
async def test_semantic_reason_fail_format():
    mock_st, _ = _mock_sentence_transformers(0.3)
    with patch.dict("sys.modules", {
        "sentence_transformers": mock_st,
        "sentence_transformers.util": mock_st.util,
    }):
        g = SemanticGrader(expected="a", threshold=0.8)
        r = await g.grade(_case(), _result("b"))
        assert "<" in r.reason


# ── LatencyGrader ──


@pytest.mark.asyncio
async def test_latency_pass():
    g = LatencyGrader(max_ms=1000)
    r = await g.grade(_case(), _result(latency_ms=500))
    assert r.passed and abs(r.score - 0.5) < 0.01


@pytest.mark.asyncio
async def test_latency_fail():
    g = LatencyGrader(max_ms=100)
    r = await g.grade(_case(), _result(latency_ms=200))
    assert not r.passed and r.score == 0.0


@pytest.mark.asyncio
async def test_latency_exact():
    g = LatencyGrader(max_ms=100)
    r = await g.grade(_case(), _result(latency_ms=100))
    assert r.passed and r.score == 0.0


@pytest.mark.asyncio
async def test_latency_zero():
    g = LatencyGrader(max_ms=100)
    r = await g.grade(_case(), _result(latency_ms=0))
    assert r.passed and r.score == 1.0


@pytest.mark.asyncio
async def test_latency_none():
    g = LatencyGrader(max_ms=100)
    res = AgentResult(output="", latency_ms=None)  # type: ignore[arg-type]
    r = await g.grade(_case(), res)
    assert not r.passed and "not recorded" in r.reason


# ── CostGrader ──


@pytest.mark.asyncio
async def test_cost_pass():
    g = CostGrader(max_usd=1.0)
    r = await g.grade(_case(), _result(cost_usd=0.5))
    assert r.passed and abs(r.score - 0.5) < 0.01


@pytest.mark.asyncio
async def test_cost_fail():
    g = CostGrader(max_usd=0.10)
    r = await g.grade(_case(), _result(cost_usd=0.20))
    assert not r.passed and r.score == 0.0


@pytest.mark.asyncio
async def test_cost_exact():
    g = CostGrader(max_usd=0.50)
    r = await g.grade(_case(), _result(cost_usd=0.50))
    assert r.passed and r.score == 0.0


@pytest.mark.asyncio
async def test_cost_none():
    g = CostGrader(max_usd=1.0)
    r = await g.grade(_case(), _result(cost_usd=None))
    assert not r.passed and "not recorded" in r.reason


@pytest.mark.asyncio
async def test_cost_zero():
    g = CostGrader(max_usd=1.0)
    r = await g.grade(_case(), _result(cost_usd=0.0))
    assert r.passed and r.score == 1.0


# ── Registry for new graders ──


def test_registry_json_schema():
    g = get_grader("json_schema", {"schema": {"type": "object"}})
    assert isinstance(g, JsonSchemaGrader)


def test_registry_semantic():
    g = get_grader("semantic", {"expected": "hello"})
    assert isinstance(g, SemanticGrader)


def test_registry_latency():
    g = get_grader("latency", {"max_ms": 500})
    assert isinstance(g, LatencyGrader)


def test_registry_cost():
    g = get_grader("cost", {"max_usd": 1.0})
    assert isinstance(g, CostGrader)
