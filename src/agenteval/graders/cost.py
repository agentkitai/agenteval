"""Cost grader — checks USD cost."""

from __future__ import annotations

from dataclasses import dataclass

from agenteval.models import EvalCase, AgentResult, GradeResult


@dataclass
class CostGrader:
    """Pass if result.cost_usd <= max_usd."""

    max_usd: float

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        if result.cost_usd is None:
            return GradeResult(passed=False, score=0.0, reason="cost not recorded")

        passed = result.cost_usd <= self.max_usd
        score = max(0.0, 1.0 - result.cost_usd / self.max_usd)
        return GradeResult(
            passed=passed,
            score=score,
            reason=f"${result.cost_usd:.4f} {'≤' if passed else '>'} ${self.max_usd:.4f}",
        )
