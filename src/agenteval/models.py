"""Core data models for AgentEval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvalCase:
    """A single evaluation case."""
    name: str
    input: str
    expected: Dict[str, Any]
    grader: str
    grader_config: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass
class EvalSuite:
    """A collection of evaluation cases."""
    name: str
    agent: str
    cases: List[EvalCase]
    defaults: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Result returned by an agent callable."""
    output: str
    tools_called: List[Dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Optional[float] = None
    latency_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GradeResult:
    """Result of grading an agent's output."""
    passed: bool
    score: float
    reason: str


@dataclass
class EvalResult:
    """Result of evaluating a single case."""
    case_name: str
    passed: bool
    score: float
    details: Dict[str, Any]
    agent_output: str
    tools_called: List[Dict[str, Any]]
    tokens_in: int
    tokens_out: int
    cost_usd: Optional[float]
    latency_ms: int


@dataclass
class EvalRun:
    """A complete evaluation run."""
    id: str
    suite: str
    agent_ref: str
    config: Dict[str, Any]
    results: List[EvalResult]
    summary: Dict[str, Any]
    created_at: str
