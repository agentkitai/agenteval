"""Deterministic run configuration profiles."""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Dict, Optional

import yaml

from agenteval.models import EvalSuite


@dataclass
class RunProfile:
    """A reusable, deterministic run configuration."""

    seed: Optional[int] = None
    sample_size: Optional[int] = None  # None = all cases
    sample_strategy: str = "all"  # all, random, first
    timeout: int = 30
    parallel: int = 1
    retries: int = 0
    retry_backoff_ms: int = 1000
    grader_defaults: Dict = field(default_factory=dict)


def load_profile(path: str) -> RunProfile:
    """Load a RunProfile from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    return RunProfile(
        seed=data.get("seed"),
        sample_size=data.get("sample_size"),
        sample_strategy=data.get("sample_strategy", "all"),
        timeout=data.get("timeout", 30),
        parallel=data.get("parallel", 1),
        retries=data.get("retries", 0),
        retry_backoff_ms=data.get("retry_backoff_ms", 1000),
        grader_defaults=data.get("grader_defaults", {}),
    )


def apply_profile(suite: EvalSuite, profile: RunProfile) -> EvalSuite:
    """Apply profile to suite: seed-based sampling, grader defaults.

    Returns a modified copy; the original suite is not mutated.
    """
    suite = copy.deepcopy(suite)

    # --- sampling ---
    cases = suite.cases

    if profile.sample_strategy == "random" and profile.sample_size is not None:
        rng = random.Random(profile.seed)
        size = min(profile.sample_size, len(cases))
        cases = rng.sample(cases, size)
    elif profile.sample_strategy == "first" and profile.sample_size is not None:
        cases = cases[: profile.sample_size]
    # "all" or no sample_size: keep all cases

    suite.cases = cases

    # --- grader defaults ---
    if profile.grader_defaults:
        default_grader = profile.grader_defaults.get("grader")
        default_config = profile.grader_defaults.get("grader_config", {})

        for case in suite.cases:
            if not case.grader and default_grader:
                case.grader = default_grader
            if not case.grader_config and default_config:
                case.grader_config = dict(default_config)

    return suite
