# AgentEval — Architecture

**Author:** Winston (Architect)  
**Date:** 2026-02-12  
**Status:** Draft — MVP

## Design Principles

1. **Local-first.** No server, no Docker, no accounts. `pip install agenteval`.
2. **Minimal dependencies.** PyYAML, Click, httpx. That's it for core.
3. **Agent-agnostic.** Don't assume LangChain, CrewAI, or any framework.
4. **File-driven.** YAML in, results in SQLite, everything version-controllable.

## Core Concepts

```
EvalSuite (YAML file)
├── EvalCase[]
│   ├── name: str
│   ├── input: str
│   ├── expected: dict (tools_called, output_contains, custom)
│   ├── grader: str (exact|contains|regex|tool-check|llm-judge|custom)
│   └── grader_config: dict
│
EvalRun (one execution of a suite)
├── id: str (ulid)
├── suite: str
├── agent_ref: str
├── timestamp: datetime
├── config: dict (model, temperature, etc. — user-provided metadata)
├── results: EvalResult[]
│   ├── case_name: str
│   ├── passed: bool
│   ├── score: float (0-1)
│   ├── details: dict (grader output, reasoning)
│   ├── agent_output: str
│   ├── tools_called: list[dict]
│   ├── tokens_in: int
│   ├── tokens_out: int
│   ├── cost_usd: float | null
│   └── latency_ms: int
└── summary: dict (pass_rate, total_cost, avg_latency)
```

## Agent Interface

MVP supports **one interface**: Python callable.

```python
from agenteval import AgentResult

async def my_agent(input: str) -> AgentResult:
    # Run your agent however you want
    return AgentResult(
        output="Flight booked: confirmation #ABC123",
        tools_called=[
            {"name": "search_flights", "args": {"from": "SFO", "to": "JFK"}},
            {"name": "book_flight", "args": {"flight_id": "UA123"}},
        ],
        tokens_in=1500,
        tokens_out=300,
        cost_usd=0.012,
        metadata={}  # anything else
    )
```

**Why only callable for MVP:**
- CLI command interface adds subprocess complexity, output parsing
- MCP client is a whole protocol implementation
- HTTP endpoint needs a server contract
- Callable is zero-overhead, maximum flexibility

The user wraps their agent in a function. They handle the framework integration. We handle the eval orchestration.

**Deferred interfaces:** CLI command, HTTP, MCP — all Phase 2+.

## File Format

```yaml
# evals/my-suite.yaml
suite: my-suite
agent: mymodule:my_agent  # Python dotted path to async callable
defaults:
  grader: llm-judge
  grader_config:
    model: gpt-4o-mini
    criteria: "Agent completed the task correctly"
cases:
  - name: case-1
    input: "Book a flight SFO to JFK"
    expected:
      tools_called: ["search_flights", "book_flight"]
    # inherits default grader
  - name: case-2
    input: "Cancel my booking ABC123"
    expected:
      output_contains: "cancelled"
    grader: contains  # override default
```

**Why YAML over TOML:** Nested structures (expected, grader_config) are more natural in YAML. Agent devs already know YAML from Docker/k8s/CI configs.

## Storage

SQLite database at `.agenteval/results.db`. Auto-created on first run.

Tables:
```sql
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    suite TEXT NOT NULL,
    agent_ref TEXT,
    config_json TEXT,
    summary_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE results (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),
    case_name TEXT NOT NULL,
    passed INTEGER NOT NULL,
    score REAL,
    details_json TEXT,
    agent_output TEXT,
    tools_json TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    latency_ms INTEGER
);
```

No migrations. If schema changes in future versions, we version the DB file or do simple ALTER TABLEs.

## Graders

```python
class Grader(Protocol):
    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        ...

@dataclass
class GradeResult:
    passed: bool
    score: float  # 0.0 - 1.0
    reason: str
```

Built-in graders:
- **ExactGrader** — `result.output == expected.output`
- **ContainsGrader** — all substrings present in output
- **RegexGrader** — output matches pattern
- **ToolCheckGrader** — expected tools were called (ordered or unordered)
- **LLMJudgeGrader** — sends output + criteria to an LLM, parses pass/fail + score
- **CustomGrader** — loads user's Python function by dotted path

## CLI

```
agenteval run <suite.yaml> [--repeat N] [--tag TAG]
agenteval list [--suite NAME]
agenteval compare <run-id-1> <run-id-2>
agenteval import-sessions <sessions.json> --output <suite.yaml>
```

`--repeat N` runs each case N times (for statistical comparison of non-deterministic agents).

## Statistical Comparison

When comparing runs with `--repeat > 1`:
- Per-case: Welch's t-test on scores, report p-value
- Aggregate: compare mean pass rates
- Flag regressions (statistically significant score drops)

Use scipy.stats if available, fall back to manual calculation. scipy is an optional dependency.

## AgentLens Integration

Optional. Not a core dependency.

`agenteval import-sessions` reads AgentLens JSON export format:
```json
[
  {
    "session_id": "...",
    "input": "user message",
    "steps": [...],
    "tools_called": [...],
    "output": "final response"
  }
]
```

Converts to YAML eval suite. The user reviews and adjusts expected values before running.

## Project Structure

```
agenteval/
├── __init__.py
├── cli.py          # Click CLI
├── models.py       # EvalSuite, EvalCase, EvalRun, EvalResult, AgentResult
├── loader.py       # YAML loading + validation
├── runner.py       # Orchestrates eval execution
├── store.py        # SQLite read/write
├── compare.py      # Run comparison + stats
├── graders/
│   ├── __init__.py
│   ├── exact.py
│   ├── contains.py
│   ├── regex.py
│   ├── tool_check.py
│   ├── llm_judge.py
│   └── custom.py
├── importers/
│   └── agentlens.py
└── py.typed
```

~15 files. That's it.

## What I Explicitly Chose NOT To Build

- **Plugin system** — graders are just classes. No registry, no entry points.
- **Config file** — no `.agenteval.toml`. Everything is in the suite YAML or CLI flags.
- **Async parallelism** — cases run sequentially in MVP. Add `--parallel` later.
- **Result export** — SQLite IS the export. Use any SQLite tool to query.
- **Web UI** — terminal output is the UI.
