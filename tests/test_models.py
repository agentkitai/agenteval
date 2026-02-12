"""Tests for agenteval.models."""

from agenteval.models import (
    AgentResult,
    EvalCase,
    EvalResult,
    EvalRun,
    EvalSuite,
    GradeResult,
)


def test_eval_case_basic():
    case = EvalCase(name="t1", input="hi", expected={"output": "hello"}, grader="exact")
    assert case.name == "t1"
    assert case.grader_config == {}


def test_eval_case_with_config():
    case = EvalCase(
        name="t1", input="hi", expected={}, grader="contains",
        grader_config={"case_sensitive": False},
    )
    assert case.grader_config == {"case_sensitive": False}


def test_eval_suite():
    cases = [EvalCase(name="c1", input="x", expected={}, grader="exact")]
    suite = EvalSuite(name="s1", agent="mod:fn", cases=cases)
    assert suite.name == "s1"
    assert suite.defaults == {}
    assert len(suite.cases) == 1


def test_agent_result_defaults():
    r = AgentResult(output="hello")
    assert r.tools_called == []
    assert r.tokens_in == 0
    assert r.cost_usd is None
    assert r.metadata == {}


def test_grade_result():
    g = GradeResult(passed=True, score=1.0, reason="match")
    assert g.passed is True
    assert g.score == 1.0


def test_eval_result():
    r = EvalResult(
        case_name="c1", passed=True, score=1.0, details={},
        agent_output="out", tools_called=[], tokens_in=10,
        tokens_out=20, cost_usd=0.01, latency_ms=100,
    )
    assert r.case_name == "c1"
    assert r.cost_usd == 0.01


def test_eval_run():
    run = EvalRun(
        id="abc", suite="s1", agent_ref="mod:fn", config={},
        results=[], summary={"pass_rate": 1.0}, created_at="2026-01-01T00:00:00Z",
    )
    assert run.id == "abc"
    assert run.summary["pass_rate"] == 1.0
