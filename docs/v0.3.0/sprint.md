# AgentEval v0.3.0 — Sprint Plan

**Author:** Bob (Engineering) | **Date:** 2026-02-13

---

## Batch Overview

| Batch | Focus | Stories | Est. Tests | Depends On |
|-------|-------|---------|------------|------------|
| 1 | Adapter Protocol + LangChain | FA-1, FA-4, FA-5 | 15 | — |
| 2 | CrewAI + AutoGen Adapters | FA-2, FA-3 | 10 | Batch 1 |
| 3 | Test Data Generation (deterministic) | TG-1, TG-2 | 20 | — |
| 4 | Test Data Generation (LLM) | TG-3, TG-4 | 10 | Batch 3 |
| 5 | Performance Profiling | PP-1, PP-2, PP-3, PP-4 | 20 | — |
| 6 | Distributed Runner | DR-1, DR-2, DR-3, DR-4 | 30 | Batch 1 (for agent_ref import) |
| **Total** | | **16 stories** | **~105 tests** | |

---

## Batch 1: Adapter Protocol + LangChain Adapter

**Stories:** FA-1, FA-4, FA-5

### Tasks

1. Create `adapters/__init__.py` with `BaseAdapter`, `get_adapter()`, `_import_agent()`
2. Create `adapters/langchain.py` with `LangChainAdapter`
3. Modify `runner.py` — add `adapter`/`agent_ref` params to `run_suite()`
4. Modify `cli.py` — add `--adapter` and `--agent` flags to `run` command
5. Add suite YAML `adapter:` key support in `loader.py`
6. Update `pyproject.toml` — add `langchain` optional extra
7. Tests: adapter protocol, import mechanism, LangChain adapter with mocks, CLI integration

### Acceptance Criteria

- [ ] `agenteval run suite.yaml --adapter langchain --agent tests.fixtures:mock_chain` works
- [ ] `BaseAdapter` subclass with `invoke()` works as custom adapter
- [ ] `pip install agentevalkit[langchain]` installs langchain-core
- [ ] Missing langchain raises helpful ImportError
- [ ] Suite YAML with `adapter: langchain` works without CLI flag

### Est. Tests: 15

---

## Batch 2: CrewAI + AutoGen Adapters

**Stories:** FA-2, FA-3

### Tasks

1. Create `adapters/crewai.py`
2. Create `adapters/autogen.py`
3. Register in `get_adapter()`
4. Update `pyproject.toml` extras
5. Tests with mocked framework objects

### Acceptance Criteria

- [ ] `--adapter crewai --agent mymodule:my_crew` invokes crew and extracts output
- [ ] `--adapter autogen --agent mymodule:my_agent` invokes agent and extracts output
- [ ] Both handle missing framework packages with clear error
- [ ] tools_called populated when framework exposes tool data

### Est. Tests: 10

---

## Batch 3: Deterministic Test Data Generation

**Stories:** TG-1, TG-2

### Tasks

1. Create `generators/__init__.py` — `MutationStrategy` base, strategy registry, `generate()`
2. Create `generators/mutations.py` — all 7 deterministic strategies
3. Add `generate` CLI command
4. Tests per strategy + integration

### Acceptance Criteria

- [ ] `agenteval generate --suite base.yaml --output expanded.yaml` produces valid YAML
- [ ] Each of 7 strategies produces expected mutations
- [ ] `--strategies empty,unicode` limits to selected strategies
- [ ] `--count 2` limits mutations per case
- [ ] Generated cases tagged `generated:strategy_name`
- [ ] Output loadable by `agenteval run`
- [ ] Deterministic: same input → same output (no randomness in non-typo strategies)

### Est. Tests: 20

---

## Batch 4: LLM Test Data Generation

**Stories:** TG-3, TG-4

### Tasks

1. Create `generators/llm_gen.py` — LLM-based adversarial generation
2. Add `llm` strategy to registry
3. Support `generate:` config in suite YAML
4. Tests with mocked LLM responses

### Acceptance Criteria

- [ ] `--strategies llm` calls LLM endpoint and produces valid cases
- [ ] Works with `OPENAI_API_KEY` env var
- [ ] `--dry-run` shows what would be generated without calling LLM
- [ ] Suite YAML `generate:` config works
- [ ] Handles LLM errors gracefully (timeout, bad response)

### Est. Tests: 10

---

## Batch 5: Performance Profiling

**Stories:** PP-1, PP-2, PP-3, PP-4

### Tasks

1. Create `profiler.py` — `Profiler` class, data models
2. Add `list_runs()` to `store.py`
3. Add `profile` CLI command with `--run`, `--trend`, `--format` flags
4. Tests for outlier detection, trend analysis, recommendations, formatting

### Acceptance Criteria

- [ ] `agenteval profile --run <id>` shows per-case table with outlier markers
- [ ] Cases >2σ flagged with ⚠️
- [ ] `agenteval profile --trend --suite <name>` shows run-over-run trends
- [ ] Recommendations printed for cases >3x average latency
- [ ] `--format json` and `--format csv` work
- [ ] Cost breakdown by grader type shown
- [ ] Works with stdlib only (no scipy)

### Est. Tests: 20

---

## Batch 6: Distributed Runner

**Stories:** DR-1, DR-2, DR-3, DR-4

### Tasks

1. Create `distributed/__init__.py`
2. Create `distributed/coordinator.py` — task pushing, result collection, fallback
3. Create `distributed/worker.py` — BRPOP loop, execution, heartbeat
4. Add `--workers` flag to `run` CLI command
5. Add `worker` CLI command
6. Update `pyproject.toml` — `distributed` extra
7. Tests with fakeredis

### Acceptance Criteria

- [ ] `agenteval run suite.yaml --workers redis://... --agent myapp:fn` distributes cases
- [ ] `agenteval worker --broker redis://...` starts worker that processes cases
- [ ] Results identical to local execution (same EvalRun schema)
- [ ] Falls back to local with warning when no workers respond within timeout
- [ ] `--worker-timeout` configurable
- [ ] Worker `--concurrency 4` processes 4 cases in parallel
- [ ] Worker heartbeat visible to coordinator
- [ ] All tests use fakeredis (no real Redis required)

### Est. Tests: 30

---

## Dependency Graph

```
Batch 1 (Adapter Protocol) ──> Batch 2 (More Adapters)
                           ──> Batch 6 (Distributed, uses agent_ref import)
Batch 3 (Deterministic Gen) ──> Batch 4 (LLM Gen)
Batch 5 (Profiling) ──> (independent)
```

**Parallel tracks:** Batches 1, 3, and 5 can start simultaneously.

---

## Totals

- **New files:** 10
- **Modified files:** 3 (cli.py, runner.py, store.py) + pyproject.toml
- **Estimated new tests:** ~105
- **New required dependencies:** 0
- **New optional dependencies:** 4 (langchain-core, crewai, pyautogen, redis)
