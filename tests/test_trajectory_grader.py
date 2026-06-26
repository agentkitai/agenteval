"""Trajectory (multi-step path) grader (#9)."""

import asyncio

from agenteval.graders import get_grader
from agenteval.graders.trajectory import TrajectoryGrader, _lcs_len
from agenteval.models import AgentResult, EvalCase


def _case(expected=None) -> EvalCase:
    return EvalCase(name="t", input="x", expected=expected or {}, grader="trajectory")


def _result(names) -> AgentResult:
    return AgentResult(output="", tools_called=[{"name": n} for n in names])


def _grade(grader, case, result):
    return asyncio.run(grader.grade(case, result))


def test_exact_path_passes():
    r = _grade(TrajectoryGrader(expected=["search", "read", "write"]), _case(), _result(["search", "read", "write"]))
    assert r.passed and r.score == 1.0


def test_reordered_path_fails_with_partial_credit():
    r = _grade(TrajectoryGrader(expected=["search", "read", "write"]), _case(), _result(["read", "search", "write"]))
    assert not r.passed and 0.0 < r.score < 1.0


def test_extra_steps_penalized_by_default():
    r = _grade(TrajectoryGrader(expected=["a", "b"]), _case(), _result(["a", "x", "b", "y"]))
    assert not r.passed and r.score == 0.5  # LCS 2 / max(2,4)


def test_allow_extra_passes_when_expected_in_order():
    r = _grade(TrajectoryGrader(expected=["a", "b"], allow_extra=True), _case(), _result(["a", "x", "b", "y"]))
    assert r.passed and r.score == 1.0


def test_max_steps_fails_an_overlong_path():
    r = _grade(TrajectoryGrader(expected=["a"], allow_extra=True, max_steps=2), _case(), _result(["a", "b", "c"]))
    assert not r.passed and "too long" in r.reason


def test_missing_step_partial_credit():
    r = _grade(TrajectoryGrader(expected=["a", "b", "c"]), _case(), _result(["a", "c"]))
    assert not r.passed and r.score == round(2 / 3, 4)


def test_empty_expected_passes():
    assert _grade(TrajectoryGrader(), _case(), _result([])).passed


def test_falls_back_to_case_expected_trajectory():
    r = _grade(TrajectoryGrader(), _case({"trajectory": ["a", "b"]}), _result(["a", "b"]))
    assert r.passed


def test_registered_in_grader_registry():
    g = get_grader("trajectory", {"expected": ["a"]})
    assert isinstance(g, TrajectoryGrader)


def test_lcs_len():
    assert _lcs_len(["a", "b", "c"], ["a", "c"]) == 2
    assert _lcs_len([], ["a"]) == 0
    assert _lcs_len(["a", "b"], ["b", "a"]) == 1
