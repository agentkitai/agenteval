"""EU AI Act testing-evidence module (#8)."""

from agenteval.eu_ai_act import EVIDENCE_KIND, build_testing_evidence, render_markdown
from agenteval.models import EvalResult, EvalRun


def _result(name: str, passed: bool, score: float, grader: str = "exact_match") -> EvalResult:
    return EvalResult(
        case_name=name, passed=passed, score=score, details={"grader": grader},
        agent_output="...", tools_called=[], tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1,
    )


def _run(results, summary=None, agent_ref="agt_x") -> EvalRun:
    return EvalRun(
        id="run_1", suite="pii-suite", agent_ref=agent_ref, config={"model": "claude-haiku-4-5"},
        results=results, summary=summary or {}, created_at="2026-06-26T00:00:00Z",
    )


def test_maps_run_to_evidence_with_computed_pass_rate():
    ev = build_testing_evidence(_run([_result("a", True, 1.0), _result("b", False, 0.0), _result("c", True, 1.0)]))
    assert ev["kind"] == EVIDENCE_KIND
    assert ev["subject"]["agentId"] == "agt_x"  # identity-bound to agent_ref by default
    assert ev["results"]["total"] == 3
    assert ev["results"]["passed"] == 2
    assert ev["results"]["failed"] == 1
    assert abs(ev["results"]["passRate"] - 2 / 3) < 1e-9
    assert ev["testingMethodology"]["graders"] == ["exact_match"]
    assert ev["contentHash"].startswith("sha256:")


def test_prefers_summary_counts_when_present():
    ev = build_testing_evidence(_run([_result("a", True, 1.0)], summary={"total": 10, "passed": 8, "failed": 2, "pass_rate": 0.8}))
    assert ev["results"]["total"] == 10
    assert ev["results"]["passRate"] == 0.8


def test_agent_id_override_binds_identity():
    ev = build_testing_evidence(_run([_result("a", True, 1.0)]), agent_id="agt_override")
    assert ev["subject"]["agentId"] == "agt_override"


def test_content_hash_is_stable_and_tamper_evident():
    run = _run([_result("a", True, 1.0), _result("b", True, 1.0)])
    h1 = build_testing_evidence(run)["contentHash"]
    h2 = build_testing_evidence(run)["contentHash"]
    assert h1 == h2  # reproducible
    # A different result set → a different hash.
    h3 = build_testing_evidence(_run([_result("a", False, 0.0), _result("b", True, 1.0)]))["contentHash"]
    assert h3 != h1


def test_render_markdown_includes_key_fields():
    md = render_markdown(build_testing_evidence(_run([_result("leaks-ssn", False, 0.0)])))
    assert "# EU AI Act — Testing Evidence" in md
    assert "leaks-ssn" in md
    assert "FAIL" in md
    assert "sha256:" in md
