"""Custom grader — imports a user-provided function."""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from agenteval.models import EvalCase, AgentResult, GradeResult


@dataclass
class CustomGrader:
    """Import and call a user function by dotted path (e.g. 'mymodule:my_grader')."""

    function: str = ""

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        if not self.function:
            return GradeResult(passed=False, score=0.0, reason="No function specified")

        if ":" not in self.function:
            return GradeResult(
                passed=False, score=0.0,
                reason=f"Invalid function path {self.function!r}. Use 'module:function' format.",
            )

        module_path, func_name = self.function.rsplit(":", 1)
        try:
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
        except (ImportError, AttributeError) as exc:
            return GradeResult(passed=False, score=0.0, reason=f"Failed to import: {exc}")

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return await func(case, result)
        return func(case, result)
