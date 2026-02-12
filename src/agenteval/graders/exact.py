"""Exact match grader."""

from __future__ import annotations

from dataclasses import dataclass

from agenteval.models import EvalCase, AgentResult, GradeResult


@dataclass
class ExactGrader:
    """Compare result.output exactly with case.expected['output']."""

    ignore_case: bool = False

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        expected = case.expected.get("output", "")
        actual = result.output

        if self.ignore_case:
            matched = actual.lower() == expected.lower()
        else:
            matched = actual == expected

        return GradeResult(
            passed=matched,
            score=1.0 if matched else 0.0,
            reason="Exact match" if matched else f"Expected {expected!r}, got {actual!r}",
        )
