"""Tool check grader."""

from __future__ import annotations

from dataclasses import dataclass

from agenteval.models import EvalCase, AgentResult, GradeResult


@dataclass
class ToolCheckGrader:
    """Check result.tools_called against case.expected['tools_called']."""

    ordered: bool = False

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        expected = case.expected.get("tools_called", [])
        if not expected:
            return GradeResult(passed=True, score=1.0, reason="No tools to check")

        actual_names = [t["name"] for t in result.tools_called]

        if self.ordered:
            # Check exact sequence (subsequence match, respecting duplicates)
            found = 0
            actual_idx = 0
            for exp in expected:
                while actual_idx < len(actual_names):
                    if actual_names[actual_idx] == exp:
                        found += 1
                        actual_idx += 1
                        break
                    actual_idx += 1
            score = found / len(expected)
            passed = found == len(expected)
        else:
            # Multiset match: respect duplicate counts
            remaining = list(actual_names)
            found = 0
            for exp in expected:
                if exp in remaining:
                    remaining.remove(exp)
                    found += 1
            score = found / len(expected)
            passed = found == len(expected)

        missing = [t for t in expected if t not in actual_names]
        return GradeResult(
            passed=passed,
            score=score,
            reason="All tools called" if passed else f"Missing tools: {missing!r}",
        )
