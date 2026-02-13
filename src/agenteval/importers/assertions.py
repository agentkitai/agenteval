"""Auto-generate assertions from AgentLens session data."""

from __future__ import annotations

from typing import Any, Dict, List


class AssertionGenerator:
    """Generates grader assertion configs from session data."""

    @staticmethod
    def from_session(session_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze a session and generate grader config assertions.

        Tool calls become ``tool_check`` assertions; final output text
        becomes ``contains`` assertions with key phrases extracted.

        Returns a list of grader config dicts ready for EvalCase.
        """
        assertions: List[Dict[str, Any]] = []
        events = session_data.get("events") or []

        # Tool call assertions
        for event in events:
            if event.get("type") != "tool_call":
                continue
            data = event.get("data") or {}
            tool_name = data.get("tool") or data.get("name")
            if not tool_name:
                continue
            assertion: Dict[str, Any] = {"type": "tool_check", "tool": tool_name}
            args = data.get("args")
            if args:
                assertion["expected_args"] = args
            assertions.append(assertion)

        # Contains assertions from output
        output = (session_data.get("output") or "").strip()
        if output:
            # Extract sentences as key phrases
            sentences = [s.strip() for s in output.replace("\n", ". ").split(". ") if s.strip()]
            if sentences:
                # Use first sentence as the contains check
                assertions.append({"type": "contains", "text": sentences[0].rstrip(".")})

        return assertions
