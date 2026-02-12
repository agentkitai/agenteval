"""Contains grader — checks substrings present in output."""

from __future__ import annotations

from dataclasses import dataclass

from agenteval.models import EvalCase, AgentResult, GradeResult


@dataclass
class ContainsGrader:
    """Check all substrings in case.expected['output_contains'] are in result.output."""

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        substrings = case.expected.get("output_contains", [])
        if not substrings:
            return GradeResult(passed=True, score=1.0, reason="No substrings to check")

        found = [s for s in substrings if s in result.output]
        score = len(found) / len(substrings)
        passed = len(found) == len(substrings)
        missing = [s for s in substrings if s not in result.output]

        return GradeResult(
            passed=passed,
            score=score,
            reason="All substrings found" if passed else f"Missing: {missing!r}",
        )
