"""JSON Schema validation grader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from agenteval.models import EvalCase, AgentResult, GradeResult


@dataclass
class JsonSchemaGrader:
    """Validate agent output as JSON against a JSON Schema."""

    schema: Optional[dict] = None
    schema_file: Optional[str] = None

    def _load_schema(self) -> dict:
        if self.schema is not None:
            return self.schema
        if self.schema_file is not None:
            with open(self.schema_file) as f:
                return json.load(f)
        raise ValueError("json_schema grader requires 'schema' or 'schema_file'")

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        import jsonschema

        schema = self._load_schema()

        try:
            data = json.loads(result.output)
        except (json.JSONDecodeError, TypeError) as exc:
            return GradeResult(passed=False, score=0.0, reason=f"Invalid JSON: {exc}")

        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as exc:
            return GradeResult(passed=False, score=0.0, reason=str(exc.message))

        return GradeResult(passed=True, score=1.0, reason="Valid")
