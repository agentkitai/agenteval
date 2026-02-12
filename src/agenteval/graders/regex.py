"""Regex grader."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from agenteval.models import EvalCase, AgentResult, GradeResult

_FLAG_MAP = {
    "IGNORECASE": re.IGNORECASE,
    "DOTALL": re.DOTALL,
    "MULTILINE": re.MULTILINE,
    "VERBOSE": re.VERBOSE,
}


@dataclass
class RegexGrader:
    """Match result.output against case.expected['pattern']."""

    flags: List[str] = field(default_factory=list)

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        pattern = case.expected.get("pattern", "")
        combined_flags = 0
        for f in self.flags:
            flag = _FLAG_MAP.get(f.upper())
            if flag is None:
                return GradeResult(passed=False, score=0.0, reason=f"Unknown flag: {f!r}")
            combined_flags |= flag

        try:
            matched = bool(re.search(pattern, result.output, combined_flags))
        except re.error as exc:
            return GradeResult(passed=False, score=0.0, reason=f"Invalid regex: {exc}")
        return GradeResult(
            passed=matched,
            score=1.0 if matched else 0.0,
            reason="Pattern matched" if matched else f"Pattern {pattern!r} not found in output",
        )
