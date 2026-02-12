"""Test helper for CustomGrader tests."""

from agenteval.models import EvalCase, AgentResult, GradeResult


async def my_grader(case: EvalCase, result: AgentResult) -> GradeResult:
    matched = result.output == case.expected.get("output", "")
    return GradeResult(passed=matched, score=1.0 if matched else 0.0, reason="custom check")
