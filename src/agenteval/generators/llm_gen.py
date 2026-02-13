"""LLM-based adversarial test case generation."""

from __future__ import annotations

import json
import logging
import warnings
from typing import List

import httpx

from agenteval.models import EvalCase

logger = logging.getLogger(__name__)

VALID_GRADERS = {"exact", "contains", "regex", "tool-check", "llm-judge", "custom"}


class LLMGenerator:
    """Generate adversarial test cases using an LLM API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def build_prompt(self, cases: list[EvalCase], count: int = 3) -> str:
        """Build the prompt sent to the LLM."""
        cases_desc = json.dumps(
            [{"name": c.name, "input": c.input, "expected": c.expected} for c in cases],
            indent=2,
        )
        return (
            f"Given these test cases for an AI agent, generate {count} adversarial "
            f"edge cases that might break the agent. Return JSON array.\n\n"
            f"Each element must have: name (str), input (str), expected (dict), grader (str).\n\n"
            f"Existing cases:\n{cases_desc}"
        )

    def generate_adversarial(
        self, cases: list[EvalCase], count: int = 3
    ) -> list[EvalCase]:
        """Call LLM to generate adversarial cases. Returns [] on any failure."""
        prompt = self.build_prompt(cases, count)
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
            if resp.status_code != 200:
                warnings.warn(f"LLM API returned {resp.status_code}, skipping LLM generation")
                return []
            content = resp.json()["choices"][0]["message"]["content"]
            items = json.loads(content)
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            warnings.warn(f"LLM API error: {e}, skipping LLM generation")
            return []
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            warnings.warn(f"Failed to parse LLM response: {e}, skipping LLM generation")
            return []

        result: List[EvalCase] = []
        for item in items:
            if len(result) >= count:
                break
            try:
                grader = item.get("grader", "exact")
                if grader not in VALID_GRADERS:
                    grader = "exact"
                result.append(EvalCase(
                    name=item.get("name", f"llm_adv_{len(result)}"),
                    input=item.get("input", ""),
                    expected=item.get("expected", {}),
                    grader=grader,
                    tags=["generated:llm"],
                ))
            except Exception:
                continue
        return result
