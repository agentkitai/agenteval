"""Trajectory (multi-step path) grader (#9).

Grades the agent's tool-call PATH against an expected ordered trajectory. Unlike
``tool-check`` (presence / subsequence of tool *names*), this scores **path
adherence**: the ordered sequence of steps, penalizing extra/unexpected steps
and (optionally) inefficient paths. The score is graded (0..1) via the
longest-common-subsequence ratio, so a near-miss path gets partial credit — the
"Agent GPA" style of trajectory evaluation. The resulting GradeResult flows into
the run and (when federated) is recorded in AgentLens's hash chain like any other
verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from agenteval.models import AgentResult, EvalCase, GradeResult


def _lcs_len(a: Sequence, b: Sequence) -> int:
    """Length of the longest common subsequence of two sequences (DP)."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        curr = [0]
        for j, y in enumerate(b):
            curr.append(prev[j] + 1 if x == y else max(prev[j + 1], curr[j]))
        prev = curr
    return prev[-1]


@dataclass
class TrajectoryGrader:
    """Score the tool-call path against ``expected`` (ordered tool names).

    Falls back to ``case.expected['trajectory']`` then ``['tools_called']`` when
    ``expected`` isn't set in config. ``allow_extra`` lets the actual path contain
    extra steps without penalty (only the expected steps must appear in order);
    otherwise extra steps lower the score. ``max_steps`` fails an over-long path.
    """

    expected: List[str] = field(default_factory=list)
    allow_extra: bool = False
    max_steps: Optional[int] = None

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        expected = list(self.expected) or case.expected.get("trajectory") or case.expected.get("tools_called", [])
        if not expected:
            return GradeResult(passed=True, score=1.0, reason="No expected trajectory to check")

        actual = [t.get("name") for t in result.tools_called]
        lcs = _lcs_len(expected, actual)
        denom = len(expected) if self.allow_extra else max(len(expected), len(actual))
        score = round(lcs / denom, 4) if denom else 1.0

        path_ok = (lcs == len(expected)) if self.allow_extra else (actual == expected)
        steps_ok = self.max_steps is None or len(actual) <= self.max_steps
        passed = path_ok and steps_ok

        if passed:
            reason = "Trajectory matches expected path"
        elif not steps_ok:
            reason = f"Path too long: {len(actual)} steps > max {self.max_steps}"
        else:
            reason = f"Path adherence {score:.2f}; expected {expected}, got {actual}"
        return GradeResult(passed=passed, score=score, reason=reason)
