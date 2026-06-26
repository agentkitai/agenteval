"""LLM-judge calibration certificate (#12; builds on the suite hash from #11).

Quantifies how well an LLM-judge's verdicts agree with reference (human) labels
on a calibration set, scoped to the EXACT dataset (the #11 suite provenance hash)
and the reference label distribution. A judge's calibration is only valid for
that dataset/distribution — and the certificate is content-hashed (optionally
HMAC-signed via AGENTEVAL_CALIBRATION_SIGNING_KEY), so the calibration claim is
*notarized*, not merely asserted (cf. DeepEval/Braintrust).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def calibration_metrics(predicted: Sequence[bool], reference: Sequence[bool]) -> Dict[str, Any]:
    """Agreement, Cohen's kappa (chance-corrected) and the confusion matrix
    between an LLM-judge's pass/fail verdicts and reference labels."""
    if len(predicted) != len(reference):
        raise ValueError("predicted and reference must be the same length")
    n = len(predicted)
    if n == 0:
        return {"n": 0, "agreement": None, "cohenKappa": None,
                "confusion": {"tp": 0, "tn": 0, "fp": 0, "fn": 0}, "precision": None, "recall": None}

    tp = tn = fp = fn = 0
    for p_raw, r_raw in zip(predicted, reference):
        p, r = bool(p_raw), bool(r_raw)
        if p and r:
            tp += 1
        elif not p and not r:
            tn += 1
        elif p and not r:
            fp += 1
        else:
            fn += 1

    agreement = (tp + tn) / n
    # Cohen's kappa: (po - pe) / (1 - pe), pe = chance agreement.
    p_pred_pos = (tp + fp) / n
    p_ref_pos = (tp + fn) / n
    pe = p_pred_pos * p_ref_pos + (1 - p_pred_pos) * (1 - p_ref_pos)
    if agreement == 1.0:
        kappa = 1.0
    elif pe >= 1.0:  # degenerate (all one class) — no chance-corrected signal
        kappa = 0.0
    else:
        kappa = (agreement - pe) / (1 - pe)

    return {
        "n": n,
        "agreement": round(agreement, 4),
        "cohenKappa": round(kappa, 4),
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
        "recall": round(tp / (tp + fn), 4) if (tp + fn) else None,
    }


def build_calibration_certificate(
    *,
    judge_model: str,
    dataset: str,
    predicted: Sequence[bool],
    reference: Sequence[bool],
    suite_hash: Optional[str] = None,
    generated_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """A notarized LLM-judge calibration certificate (pure). Content-hashed and,
    when ``AGENTEVAL_CALIBRATION_SIGNING_KEY`` is set, HMAC-signed."""
    metrics = calibration_metrics(predicted, reference)
    ref_pos = sum(1 for r in reference if bool(r))
    core: Dict[str, Any] = {
        "kind": "agenteval.llm-judge-calibration/v1",
        "judgeModel": judge_model,
        "dataset": dataset,
        "suiteHash": suite_hash,
        "referenceDistribution": {"positive": ref_pos, "negative": len(reference) - ref_pos},
        "metrics": metrics,
        "generatedAt": (generated_at or datetime.now(timezone.utc)).isoformat(),
    }
    canon = _canonical(core)
    core["contentHash"] = "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()
    key = os.environ.get("AGENTEVAL_CALIBRATION_SIGNING_KEY")
    if key:
        value = hmac.new(key.encode("utf-8"), canon.encode("utf-8"), hashlib.sha256).hexdigest()
        core["signature"] = {"type": "hmac", "alg": "sha256", "value": value}
    else:
        core["signature"] = None
    return core
