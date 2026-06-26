"""Suite/dataset provenance hashing for reproducibility (EU AI Act Art.10) (#11).

A deterministic content hash of an EvalSuite — its cases
(name/input/expected/grader/grader_config/tags) plus name/agent/defaults — so a
run can record EXACTLY which suite version produced it, and CI can detect drift
("the dataset changed since the last approved run"). Sorted-key canonical JSON
makes the hash reproducible across machines and runs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agenteval.models import EvalSuite


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def suite_content_hash(suite: EvalSuite) -> str:
    """Reproducible ``sha256:…`` fingerprint of a suite's content.

    Order-sensitive over cases (a reorder is a real change). Independent of how
    the suite was loaded, so the same YAML/JSON always yields the same hash.
    """
    body = {
        "name": suite.name,
        "agent": suite.agent,
        "defaults": suite.defaults,
        "cases": [
            {
                "name": c.name,
                "input": c.input,
                "expected": c.expected,
                "grader": c.grader,
                "grader_config": c.grader_config,
                "tags": list(c.tags),
            }
            for c in suite.cases
        ],
    }
    return "sha256:" + hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
