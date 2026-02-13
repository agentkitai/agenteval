"""Test data generators for AgentEval."""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from agenteval.models import EvalCase, EvalSuite


class MutationStrategy(ABC):
    """Base class for mutation strategies."""

    @abstractmethod
    def mutate(self, input: str) -> list[str]:
        """Return list of mutated versions of input."""
        ...


_STRATEGY_REGISTRY: Dict[str, type] = {}


def _ensure_registry() -> None:
    if _STRATEGY_REGISTRY:
        return
    from agenteval.generators.mutations import (
        EmptyStrategy,
        MaxLengthStrategy,
        NegationStrategy,
        PromptInjectionStrategy,
        SqlInjectionStrategy,
        TypoStrategy,
        UnicodeStrategy,
    )
    _STRATEGY_REGISTRY.update({
        "empty": EmptyStrategy,
        "max_length": MaxLengthStrategy,
        "unicode": UnicodeStrategy,
        "sql_injection": SqlInjectionStrategy,
        "prompt_injection": PromptInjectionStrategy,
        "typo": TypoStrategy,
        "negation": NegationStrategy,
    })


def get_strategy(name: str) -> MutationStrategy:
    """Get a strategy instance by name."""
    _ensure_registry()
    if name not in _STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {name!r}. Available: {sorted(_STRATEGY_REGISTRY)}")
    return _STRATEGY_REGISTRY[name]()


def generate(
    suite: EvalSuite,
    strategies: Optional[List[str]] = None,
    count: Optional[int] = None,
) -> EvalSuite:
    """Generate mutated cases from a suite.

    Args:
        suite: Source suite.
        strategies: Strategy names to use (default: all).
        count: Max mutations per strategy per case (default: unlimited).

    Returns:
        New EvalSuite with original + generated cases.
    """
    _ensure_registry()
    strategy_names = strategies or list(_STRATEGY_REGISTRY.keys())
    strats = [get_strategy(n) for n in strategy_names]

    new_cases = list(suite.cases)
    for case in suite.cases:
        for sname, strat in zip(strategy_names, strats):
            mutations = strat.mutate(case.input)
            if count is not None:
                mutations = mutations[:count]
            for i, mutated_input in enumerate(mutations):
                new_case = EvalCase(
                    name=f"{case.name}__{sname}_{i}",
                    input=mutated_input,
                    expected=dict(case.expected),
                    grader=case.grader,
                    grader_config=dict(case.grader_config),
                    tags=list(case.tags) + [f"generated:{sname}"],
                )
                new_cases.append(new_case)

    return EvalSuite(
        name=suite.name,
        agent=suite.agent,
        cases=new_cases,
        defaults=dict(suite.defaults),
    )
