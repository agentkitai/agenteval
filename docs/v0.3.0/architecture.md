# AgentEval v0.3.0 — Architecture Document

**Author:** Winston (Architecture) | **Date:** 2026-02-13

---

## Overview

Four new modules integrate into the existing structure. No changes to core models or graders. The runner gains an adapter layer and distributed backend. Two new CLI command groups: `generate` and `profile`.

```
src/agenteval/
├── adapters/              # NEW — Framework adapters
│   ├── __init__.py        # BaseAdapter protocol, get_adapter()
│   ├── langchain.py       # LangChain adapter
│   ├── crewai.py          # CrewAI adapter
│   └── autogen.py         # AutoGen adapter
├── generators/            # NEW — Test data generation
│   ├── __init__.py        # Strategy registry, generate()
│   ├── mutations.py       # Deterministic mutation strategies
│   └── llm_gen.py         # LLM-based adversarial generation
├── profiler.py            # NEW — Performance profiling
├── distributed/           # NEW — Distributed runner
│   ├── __init__.py
│   ├── coordinator.py     # Pushes tasks, collects results
│   └── worker.py          # Worker process loop
├── cli.py                 # MODIFIED — new commands + --adapter/--agent flags
├── runner.py              # MODIFIED — adapter integration
└── ... (existing unchanged)
```

---

## 1. Framework Adapters

### Design

```python
# adapters/__init__.py
from agenteval.models import AgentResult

class BaseAdapter:
    """Protocol for framework adapters."""
    def __init__(self, agent_ref: str):
        """agent_ref is a dotted import path like 'myapp.chains:qa_chain'."""
        self.agent = self._import_agent(agent_ref)

    def _import_agent(self, ref: str):
        """Import 'module.path:attribute' and return the object."""
        module_path, _, attr = ref.rpartition(":")
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    async def invoke(self, input_text: str) -> AgentResult:
        raise NotImplementedError

def get_adapter(name: str, agent_ref: str) -> BaseAdapter:
    adapters = {
        "langchain": "agenteval.adapters.langchain:LangChainAdapter",
        "crewai": "agenteval.adapters.crewai:CrewAIAdapter",
        "autogen": "agenteval.adapters.autogen:AutoGenAdapter",
    }
    # lazy import to avoid pulling in framework deps
    ...
```

### LangChain Adapter (example)

```python
# adapters/langchain.py
import time
from agenteval.models import AgentResult
from agenteval.adapters import BaseAdapter

class LangChainAdapter(BaseAdapter):
    async def invoke(self, input_text: str) -> AgentResult:
        try:
            from langchain_core.runnables import Runnable
        except ImportError:
            raise ImportError("Install with: pip install agentevalkit[langchain]")

        start = time.perf_counter()
        # Support both sync and async
        if hasattr(self.agent, 'ainvoke'):
            response = await self.agent.ainvoke(input_text)
        else:
            response = self.agent.invoke(input_text)
        latency = int((time.perf_counter() - start) * 1000)

        # Extract output — handle str, AIMessage, dict
        output = self._extract_output(response)
        return AgentResult(output=output, latency_ms=latency)

    def _extract_output(self, response) -> str:
        if isinstance(response, str):
            return response
        if hasattr(response, 'content'):
            return response.content
        if isinstance(response, dict) and 'output' in response:
            return response['output']
        return str(response)
```

### Runner Integration

The runner's `run_suite` gets an optional `adapter` parameter. When provided, it wraps the adapter's `invoke` as the `AgentCallable`:

```python
# In runner.py — add to run_suite signature:
async def run_suite(suite, agent_fn=None, *, adapter=None, agent_ref=None, ...):
    if adapter and agent_fn is None:
        from agenteval.adapters import get_adapter
        _adapter = get_adapter(adapter, agent_ref)
        agent_fn = _adapter.invoke
```

### Test Strategy

- Mock each framework's objects (no real LangChain/CrewAI in tests)
- Test BaseAdapter._import_agent with a test module
- Test each adapter's _extract_output with various response shapes
- Test ImportError messaging
- **~25 tests**

---

## 2. Test Data Generation

### Design

```python
# generators/__init__.py
from agenteval.models import EvalCase
from typing import List

class MutationStrategy:
    name: str
    def mutate(self, case: EvalCase) -> List[EvalCase]: ...

BUILTIN_STRATEGIES = {
    "empty": EmptyInputStrategy,
    "max_length": MaxLengthStrategy,
    "unicode": UnicodeStrategy,
    "sql_injection": SqlInjectionStrategy,
    "prompt_injection": PromptInjectionStrategy,
    "typos": TypoStrategy,
    "negation": NegationStrategy,
}

def generate(cases: List[EvalCase], strategies: List[str], count: int = 3) -> List[EvalCase]:
    ...
```

### Mutation Details

| Strategy | Input Mutation | Expected Behavior |
|----------|---------------|-------------------|
| `empty` | `""` | Agent handles gracefully (no crash) |
| `max_length` | Input repeated to 10K chars | Agent handles gracefully |
| `unicode` | Inject emoji, RTL, zero-width chars | Agent handles gracefully |
| `sql_injection` | Classic SQL payloads appended | Agent doesn't execute SQL |
| `prompt_injection` | "Ignore previous instructions..." | Agent maintains behavior |
| `typos` | Random char swaps/insertions | Agent still understands |
| `negation` | Negate the request ("don't", "never") | Different output than original |

Generated cases use grader `contains` with `expected: {should_not_contain: "error"}` or a custom grader config indicating "should not crash."

### LLM Generation

```python
# generators/llm_gen.py
class LlmStrategy(MutationStrategy):
    name = "llm"

    async def mutate(self, case: EvalCase) -> List[EvalCase]:
        prompt = f"""Given this test case input: "{case.input}"
        Generate 3 adversarial variations that might break an AI agent.
        Return as JSON array of strings."""
        # Use httpx to call OpenAI-compatible endpoint
        ...
```

### CLI

```
agenteval generate --suite base.yaml --output expanded.yaml [--strategies empty,unicode] [--count 3]
```

### Test Strategy

- Test each mutation strategy in isolation
- Test generate() combines strategies correctly
- Test YAML output is valid and loadable
- Test tagging (generated:strategy)
- Test --count limiting
- Mock LLM for llm strategy tests
- **~30 tests**

---

## 3. Performance Profiling

### Design

Single module `profiler.py` that reads from the SQLite store.

```python
# profiler.py
from agenteval.store import ResultStore
from statistics import mean, stdev
from typing import Optional

class Profiler:
    def __init__(self, store: ResultStore):
        self.store = store

    def profile_run(self, run_id: str) -> ProfileReport:
        """Per-case breakdown with outlier detection."""
        run = self.store.load_run(run_id)
        latencies = [r.latency_ms for r in run.results]
        avg = mean(latencies)
        sd = stdev(latencies) if len(latencies) > 1 else 0
        cases = []
        for r in run.results:
            is_outlier = r.latency_ms > avg + 2 * sd if sd > 0 else False
            cases.append(CaseProfile(
                name=r.case_name, latency_ms=r.latency_ms,
                cost_usd=r.cost_usd, tokens_in=r.tokens_in,
                tokens_out=r.tokens_out, is_outlier=is_outlier,
            ))
        recommendations = self._generate_recommendations(cases, avg)
        return ProfileReport(cases=cases, avg_latency=avg, recommendations=recommendations)

    def trend(self, suite_name: str, last_n: int = 10) -> TrendReport:
        """Latency/cost trends across runs."""
        ...

    def _generate_recommendations(self, cases, avg) -> list[str]:
        recs = []
        for c in cases:
            if c.latency_ms > avg * 3:
                recs.append(f"Case '{c.name}' is {c.latency_ms/avg:.1f}x slower than average ({c.latency_ms}ms vs {avg:.0f}ms avg). Consider caching or simplifying.")
        return recs
```

### Data Models

```python
@dataclass
class CaseProfile:
    name: str
    latency_ms: int
    cost_usd: Optional[float]
    tokens_in: int
    tokens_out: int
    is_outlier: bool

@dataclass
class ProfileReport:
    cases: List[CaseProfile]
    avg_latency: float
    std_latency: float
    recommendations: List[str]

@dataclass
class TrendReport:
    runs: List[RunSummary]  # id, created_at, pass_rate, avg_latency, total_cost
```

### Store Changes

Add method to `ResultStore`:
```python
def list_runs(self, suite: Optional[str] = None, limit: int = 10) -> List[EvalRun]:
    """List recent runs, optionally filtered by suite name."""
```

### Test Strategy

- Test outlier detection with known data
- Test recommendations generation
- Test trend with multiple runs
- Test output formatting (table, json, csv)
- Test edge cases (1 case, all same latency, no cost data)
- **~20 tests**

---

## 4. Distributed Runner

### Design

Simple Redis list-based task queue. No framework dependencies beyond `redis` package.

```
Coordinator                    Redis                     Worker(s)
    │                            │                          │
    ├─ LPUSH tasks ──────────>   │                          │
    │                            │  <──── BRPOP tasks ──────┤
    │                            │                          ├─ execute case
    │                            │  <──── LPUSH results ────┤
    ├─ BRPOP results <────────   │                          │
    ├─ merge into EvalRun        │                          │
```

### Task Schema

```json
{
  "run_id": "abc123",
  "case": {
    "name": "test_1",
    "input": "hello",
    "expected": {"contains": "hi"},
    "grader": "contains",
    "grader_config": {}
  },
  "agent_ref": "myapp.agent:main",
  "adapter": "langchain",
  "timeout": 30.0
}
```

### Result Schema

```json
{
  "run_id": "abc123",
  "result": {
    "case_name": "test_1",
    "passed": true,
    "score": 1.0,
    "details": {"reason": "Output contains 'hi'"},
    "agent_output": "hi there!",
    "tools_called": [],
    "tokens_in": 10,
    "tokens_out": 5,
    "cost_usd": 0.001,
    "latency_ms": 150
  }
}
```

### Coordinator

```python
# distributed/coordinator.py
import json
from agenteval.models import EvalCase, EvalResult, EvalRun

class Coordinator:
    def __init__(self, redis_url: str, timeout: int = 300):
        import redis
        self.redis = redis.from_url(redis_url)
        self.timeout = timeout

    async def distribute(self, suite, agent_ref, adapter=None, run_id=None) -> EvalRun:
        # 1. Push all cases to agenteval:tasks
        # 2. Wait for results on agenteval:results:{run_id}
        # 3. If timeout, fall back to local for remaining
        # 4. Merge and return EvalRun
        ...

    def list_workers(self) -> list[dict]:
        # Read from agenteval:workers (SET with TTL entries)
        ...
```

### Worker

```python
# distributed/worker.py
class Worker:
    def __init__(self, broker_url: str, concurrency: int = 1):
        import redis
        self.redis = redis.from_url(broker_url)
        self.concurrency = concurrency

    async def run(self):
        """Main worker loop — BRPOP tasks, execute, push results."""
        while True:
            task_data = self.redis.brpop("agenteval:tasks", timeout=5)
            if task_data is None:
                self._heartbeat()
                continue
            task = json.loads(task_data[1])
            result = await self._execute(task)
            self.redis.lpush(f"agenteval:results:{task['run_id']}", json.dumps(result))
```

### CLI Integration

```
agenteval run suite.yaml --adapter langchain --agent myapp:chain --workers redis://localhost:6379
agenteval worker --broker redis://localhost:6379 [--concurrency 4]
```

### Test Strategy

- Use `fakeredis` for all Redis tests (no real Redis needed)
- Test task serialization/deserialization roundtrip
- Test coordinator fallback when no workers respond
- Test worker processes a task and pushes result
- Test result merging produces valid EvalRun
- Test heartbeat mechanism
- Integration test: coordinator + worker in-process with fakeredis
- **~30 tests**

---

## Dependency Analysis

| Package | Feature | Required? | Extra Name |
|---------|---------|-----------|------------|
| `langchain-core` | LangChain adapter | Optional | `langchain` |
| `crewai` | CrewAI adapter | Optional | `crewai` |
| `pyautogen` | AutoGen adapter | Optional | `autogen` |
| `redis` | Distributed runner | Optional | `distributed` |
| `fakeredis` | Distributed tests | Dev only | — |

**pyproject.toml additions:**

```toml
[project.optional-dependencies]
langchain = ["langchain-core>=0.1"]
crewai = ["crewai>=0.1"]
autogen = ["pyautogen>=0.2"]
distributed = ["redis>=4.5"]
dev = ["pytest>=7.0", "pytest-asyncio>=0.21", "ruff>=0.1", "build", "fakeredis>=2.0"]
```

**Zero new required dependencies.** Core `dependencies` list unchanged.

---

## Integration Points

| New Module | Touches | Nature of Change |
|------------|---------|-----------------|
| adapters/ | runner.py, cli.py | Runner accepts adapter param; CLI adds flags |
| generators/ | cli.py, loader.py | CLI adds `generate` command; loader used to read input suite |
| profiler.py | cli.py, store.py | CLI adds `profile` command; store gets `list_runs()` |
| distributed/ | runner.py, cli.py | Runner delegates to coordinator; CLI adds flags + `worker` command |

No changes to: models.py, graders/, formatters/, importers/, compare.py, ci.py, badge.py, github.py.

**One addition to store.py:** `list_runs()` method (~15 lines).
