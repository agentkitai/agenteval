"""Latency grader — checks response time."""

from __future__ import annotations

from dataclasses import dataclass

from agenteval.models import EvalCase, AgentResult, GradeResult


@dataclass
class LatencyGrader:
    """Pass if result.latency_ms <= max_ms."""

    max_ms: float

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        if result.latency_ms is None:
            return GradeResult(passed=False, score=0.0, reason="latency not recorded")

        passed = result.latency_ms <= self.max_ms
        score = max(0.0, 1.0 - result.latency_ms / self.max_ms)
        return GradeResult(
            passed=passed,
            score=score,
            reason=f"{result.latency_ms}ms {'≤' if passed else '>'} {self.max_ms}ms",
        )
