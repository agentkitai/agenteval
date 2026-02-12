"""LLM Judge grader — uses an LLM to evaluate agent output."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx

from agenteval.models import EvalCase, AgentResult, GradeResult

_PROMPT_TEMPLATE = """You are an evaluation judge. Assess the agent's output.

## Input
{input}

## Expected Behavior
{expected}

## Agent Output
{output}

## Criteria
{criteria}

Respond ONLY with JSON: {{"passed": true/false, "score": 0.0-1.0, "reason": "..."}}"""


@dataclass
class LLMJudgeGrader:
    """Send agent output to an LLM for evaluation."""

    model: str = "gpt-4o-mini"
    criteria: str = "Is the output correct and complete?"
    api_url: str = "https://api.openai.com/v1/chat/completions"
    api_key: str = ""

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        api_key = self.api_key or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return GradeResult(passed=False, score=0.0, reason="No API key provided")

        prompt = _PROMPT_TEMPLATE.format(
            input=case.input,
            expected=json.dumps(case.expected),
            output=result.output,
            criteria=self.criteria,
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.api_url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                },
                timeout=30.0,
            )
            resp.raise_for_status()

        body = resp.json()
        content = body["choices"][0]["message"]["content"]

        try:
            parsed = json.loads(content)
            return GradeResult(
                passed=bool(parsed["passed"]),
                score=float(parsed["score"]),
                reason=str(parsed.get("reason", "")),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            return GradeResult(
                passed=False,
                score=0.0,
                reason=f"Failed to parse LLM response: {exc}. Raw: {content[:200]}",
            )
