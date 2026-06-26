"""LLM-judge calibration certificate (#12)."""

import pytest

from agenteval.calibration import build_calibration_certificate, calibration_metrics


def test_perfect_agreement():
    m = calibration_metrics([True, False, True], [True, False, True])
    assert m["n"] == 3
    assert m["agreement"] == 1.0
    assert m["cohenKappa"] == 1.0
    assert m["confusion"] == {"tp": 2, "tn": 1, "fp": 0, "fn": 0}


def test_total_disagreement_has_negative_kappa():
    m = calibration_metrics([True, True, False, False], [False, False, True, True])
    assert m["agreement"] == 0.0
    assert m["cohenKappa"] < 0  # worse than chance


def test_confusion_and_precision_recall():
    # predicted P,P,P,N vs reference P,N,P,P → tp=2, fp=1, fn=1, tn=0
    m = calibration_metrics([True, True, True, False], [True, False, True, True])
    assert m["confusion"] == {"tp": 2, "tn": 0, "fp": 1, "fn": 1}
    assert m["precision"] == round(2 / 3, 4)
    assert m["recall"] == round(2 / 3, 4)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        calibration_metrics([True], [True, False])


def test_empty_is_null_metrics():
    m = calibration_metrics([], [])
    assert m["n"] == 0 and m["agreement"] is None and m["cohenKappa"] is None


def test_degenerate_single_class_kappa_zero():
    # all predicted+reference negative → agreement 1.0 short-circuits to kappa 1.0
    assert calibration_metrics([False, False], [False, False])["cohenKappa"] == 1.0
    # predicted all P, reference all P but one N → pe high; not perfect
    m = calibration_metrics([True, True], [True, False])
    assert m["agreement"] == 0.5


def test_certificate_shape_and_hash(monkeypatch):
    monkeypatch.delenv("AGENTEVAL_CALIBRATION_SIGNING_KEY", raising=False)
    c = build_calibration_certificate(
        judge_model="claude-haiku-4-5", dataset="pii-suite",
        predicted=[True, False], reference=[True, True], suite_hash="sha256:abc",
    )
    assert c["kind"] == "agenteval.llm-judge-calibration/v1"
    assert c["judgeModel"] == "claude-haiku-4-5"
    assert c["suiteHash"] == "sha256:abc"
    assert c["referenceDistribution"] == {"positive": 2, "negative": 0}
    assert c["metrics"]["n"] == 2
    assert c["contentHash"].startswith("sha256:")
    assert c["signature"] is None


def test_certificate_signed_with_key(monkeypatch):
    monkeypatch.setenv("AGENTEVAL_CALIBRATION_SIGNING_KEY", "calib-key-at-least-16-chars")
    c = build_calibration_certificate(judge_model="m", dataset="d", predicted=[True], reference=[True])
    assert c["signature"]["type"] == "hmac" and len(c["signature"]["value"]) == 64


def test_command_registered():
    from click.testing import CliRunner

    from agenteval.cli import cli

    res = CliRunner().invoke(cli, ["calibrate", "--help"])
    assert res.exit_code == 0
    assert "calibration certificate" in res.output.lower()
