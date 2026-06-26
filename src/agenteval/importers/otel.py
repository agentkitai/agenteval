"""Import OTel GenAI traces as eval fixtures / trajectories (#15).

Reads an OTLP trace export (JSON: resourceSpans → scopeSpans → spans) and turns
each trace into an EvalCase — input from the GenAI prompt, expected output from
the completion, and the ordered tool calls as a trajectory. This is fixture
*ingestion*, NOT a trace dashboard (an explicit anti-goal): the output is a
replayable eval suite, nothing more.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional

from agenteval.models import EvalCase, EvalSuite


class OtelImportError(Exception):
    """Raised when an OTLP trace file can't be read or parsed."""


def _attr(attrs: List[Dict[str, Any]], key: str) -> Optional[str]:
    """Read a string-valued OTLP attribute (attrs are [{key, value:{stringValue}}])."""
    for kv in attrs:
        if kv.get("key") == key:
            v = kv.get("value") or {}
            sv = v.get("stringValue")
            return sv if isinstance(sv, str) else None
    return None


def _text_of(value: Any) -> str:
    """Coerce a message content (str, or a list of content parts) to text."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in value]
        return " ".join(p for p in parts if p)
    return ""


def _messages_content(raw: Optional[str], role: str) -> Optional[str]:
    """Last message with `role` from a gen_ai.{input,output}.messages JSON attr."""
    if not raw:
        return None
    try:
        msgs = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(msgs, list):
        return None
    found = [_text_of(m.get("content")) for m in msgs if isinstance(m, dict) and m.get("role") == role]
    found = [t for t in found if t.strip()]
    return found[-1] if found else None


def _indexed(attrs: List[Dict[str, Any]], kind: str, role: str) -> Optional[str]:
    """OpenLLMetry indexed style: gen_ai.{prompt,completion}.{i}.content for a role."""
    out: List[str] = []
    for i in range(64):
        r = _attr(attrs, f"gen_ai.{kind}.{i}.role")
        c = _attr(attrs, f"gen_ai.{kind}.{i}.content")
        if r is None and c is None:
            break
        if c and (r == role or r is None):
            out.append(c)
    return out[-1] if out else None


def _extract_prompt(attrs: List[Dict[str, Any]]) -> Optional[str]:
    return (
        _messages_content(_attr(attrs, "gen_ai.input.messages"), "user")
        or _indexed(attrs, "prompt", "user")
        or _attr(attrs, "gen_ai.prompt")
    )


def _extract_output(attrs: List[Dict[str, Any]]) -> Optional[str]:
    return (
        _messages_content(_attr(attrs, "gen_ai.output.messages"), "assistant")
        or _indexed(attrs, "completion", "assistant")
        or _attr(attrs, "gen_ai.completion")
    )


def _trace_to_case(trace_id: str, spans: List[Dict[str, Any]], grader: str) -> Optional[EvalCase]:
    model: Optional[str] = None
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    tools: List[str] = []

    for span in spans:
        attrs = span.get("attributes") or []
        model = _attr(attrs, "gen_ai.request.model") or model
        if _attr(attrs, "gen_ai.operation.name") == "execute_tool" or _attr(attrs, "gen_ai.tool.name"):
            tools.append(_attr(attrs, "gen_ai.tool.name") or span.get("name") or "tool")
        if input_text is None:
            input_text = _extract_prompt(attrs)
        out = _extract_output(attrs)
        if out:
            output_text = out  # last completion in the trace wins

    if not input_text or not input_text.strip():
        return None

    expected: Dict[str, Any] = {}
    if output_text and output_text.strip():
        expected["output"] = output_text.strip()
    if tools:
        expected["tools"] = tools

    # A trace with tool calls is a trajectory; otherwise a plain replay fixture.
    effective_grader = "tool-check" if (tools and grader == "contains") else grader
    tags = ["imported", "otel"] + ([model] if model else [])
    return EvalCase(
        name=f"otel_{(trace_id or 'trace')[:8]}",
        input=input_text.strip(),
        expected=expected,
        grader=effective_grader,
        tags=tags,
    )


def _all_spans(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    spans: List[Dict[str, Any]] = []
    for rs in data.get("resourceSpans") or []:
        for ss in rs.get("scopeSpans") or []:
            spans.extend(ss.get("spans") or [])
    return spans


def import_otel(
    *,
    file_path: str,
    suite_name: str = "otel-import",
    grader: str = "contains",
    limit: Optional[int] = None,
) -> EvalSuite:
    """Load an OTLP traces JSON file and build an EvalSuite (one case per trace)."""
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise OtelImportError(f"reading {file_path}: {e}") from e
    if not isinstance(data, dict):
        raise OtelImportError("OTLP trace file must be a JSON object")

    by_trace: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for span in _all_spans(data):
        by_trace[str(span.get("traceId", ""))].append(span)

    cases: List[EvalCase] = []
    for trace_id, spans in by_trace.items():
        spans.sort(key=lambda s: int(s.get("startTimeUnixNano") or 0))
        case = _trace_to_case(trace_id, spans, grader)
        if case:
            cases.append(case)
        if limit and len(cases) >= limit:
            break

    return EvalSuite(name=suite_name, agent="otel-import", cases=cases)
