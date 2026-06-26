"""OTel GenAI trace → eval fixtures/trajectories (#15)."""

import json

import pytest

from agenteval.importers.otel import OtelImportError, _trace_to_case, import_otel


def _attr(key, val):
    return {"key": key, "value": {"stringValue": val}}


def _span(trace_id, name, attrs, start=1):
    return {"traceId": trace_id, "name": name, "startTimeUnixNano": str(start), "attributes": attrs}


def _llm_span(trace_id, model="gpt-4o", user="What is 2+2?", assistant="4", start=1):
    return _span(trace_id, "chat", [
        _attr("gen_ai.request.model", model),
        _attr("gen_ai.input.messages", json.dumps([{"role": "user", "content": user}])),
        _attr("gen_ai.output.messages", json.dumps([{"role": "assistant", "content": assistant}])),
    ], start)


def _tool_span(trace_id, tool="calculator", start=2):
    return _span(trace_id, "tool", [
        _attr("gen_ai.operation.name", "execute_tool"),
        _attr("gen_ai.tool.name", tool),
    ], start)


def test_trace_to_case_replay_fixture():
    case = _trace_to_case("trace123", [_llm_span("trace123")], "contains")
    assert case is not None
    assert case.input == "What is 2+2?"
    assert case.expected["output"] == "4"
    assert case.grader == "contains"
    assert "otel" in case.tags and "gpt-4o" in case.tags


def test_trace_with_tools_becomes_trajectory():
    spans = [_llm_span("t1", start=1), _tool_span("t1", "calculator", start=2), _tool_span("t1", "search", start=3)]
    case = _trace_to_case("t1", spans, "contains")
    assert case.expected["tools"] == ["calculator", "search"]
    assert case.grader == "tool-check"  # contains + tools → tool-check


def test_indexed_openllmetry_style():
    span = _span("t2", "chat", [
        _attr("gen_ai.prompt.0.role", "user"),
        _attr("gen_ai.prompt.0.content", "hello"),
        _attr("gen_ai.completion.0.role", "assistant"),
        _attr("gen_ai.completion.0.content", "hi there"),
    ])
    case = _trace_to_case("t2", [span], "contains")
    assert case.input == "hello"
    assert case.expected["output"] == "hi there"


def test_span_without_input_is_skipped():
    span = _span("t3", "noop", [_attr("gen_ai.request.model", "gpt-4o")])
    assert _trace_to_case("t3", [span], "contains") is None


def test_import_otel_groups_by_trace(tmp_path):
    payload = {
        "resourceSpans": [
            {"scopeSpans": [{"spans": [
                _llm_span("traceA", user="Q-A", assistant="A-A"),
                _llm_span("traceB", user="Q-B", assistant="A-B"),
                _tool_span("traceB", "search"),
            ]}]}
        ]
    }
    f = tmp_path / "traces.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    suite = import_otel(file_path=str(f), suite_name="s")
    assert suite.name == "s"
    assert len(suite.cases) == 2  # one per trace
    by_input = {c.input: c for c in suite.cases}
    assert by_input["Q-B"].expected["tools"] == ["search"]


def test_import_otel_bad_file_raises(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not json", encoding="utf-8")
    with pytest.raises(OtelImportError):
        import_otel(file_path=str(f))
