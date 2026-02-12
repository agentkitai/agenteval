"""Grader protocol and registry for AgentEval."""

from __future__ import annotations

from typing import Protocol, Dict

from agenteval.models import EvalCase, AgentResult, GradeResult


class Grader(Protocol):
    """Protocol that all graders must satisfy."""

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult: ...


_GRADER_REGISTRY: Dict[str, type] = {}


def _ensure_registry() -> None:
    if _GRADER_REGISTRY:
        return
    from agenteval.graders.exact import ExactGrader
    from agenteval.graders.contains import ContainsGrader
    from agenteval.graders.regex import RegexGrader
    from agenteval.graders.tool_check import ToolCheckGrader
    from agenteval.graders.llm_judge import LLMJudgeGrader
    from agenteval.graders.custom import CustomGrader

    _GRADER_REGISTRY.update({
        "exact": ExactGrader,
        "contains": ContainsGrader,
        "regex": RegexGrader,
        "tool-check": ToolCheckGrader,
        "llm-judge": LLMJudgeGrader,
        "custom": CustomGrader,
    })


def get_grader(name: str, config: dict) -> Grader:
    """Get a grader instance by name."""
    _ensure_registry()
    if name not in _GRADER_REGISTRY:
        raise ValueError(f"Unknown grader: {name!r}. Available: {sorted(_GRADER_REGISTRY)}")
    return _GRADER_REGISTRY[name](**config)
