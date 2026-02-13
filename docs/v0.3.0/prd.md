# AgentEval v0.3.0 — Product Requirements Document

**Author:** John (Product) | **Date:** 2026-02-13

---

## 1. Framework Adapters

### User Stories

- **FA-1:** As a LangChain user, I can run `agenteval run suite.yaml --adapter langchain --agent mymodule:my_chain` without writing a custom callable.
- **FA-2:** As a CrewAI user, I can evaluate my crew with `--adapter crewai --agent mymodule:my_crew`.
- **FA-3:** As an AutoGen user, I can evaluate my agent with `--adapter autogen --agent mymodule:my_agent`.
- **FA-4:** As a developer, I can create a custom adapter by implementing `BaseAdapter.invoke(input: str) -> AgentResult`.
- **FA-5:** As a user, I can install only the adapter I need: `pip install agentevalkit[langchain]`.

### Functional Requirements

- **FR-1.1:** Adapter protocol defines `BaseAdapter` with method `invoke(input: str) -> AgentResult`.
- **FR-1.2:** CLI accepts `--adapter <name>` and `--agent <dotted.path:object>` flags on `run` command.
- **FR-1.3:** When `--adapter` is provided, `--agent` specifies a Python import path to the framework object (e.g., `myapp.chains:qa_chain`).
- **FR-1.4:** LangChain adapter calls `.invoke()` or `.ainvoke()`, extracts output text, latency, token usage, and cost from callback data.
- **FR-1.5:** CrewAI adapter calls `.kickoff()`, extracts final output and task results.
- **FR-1.6:** AutoGen adapter sends a message to the agent and collects the reply.
- **FR-1.7:** If the framework package is not installed, adapter import raises `ImportError` with a helpful message: "Install with: pip install agentevalkit[langchain]".
- **FR-1.8:** Adapters populate `AgentResult.tools_called` when the framework exposes tool/function call data.
- **FR-1.9:** Adapter can be specified in suite YAML under `adapter:` key as alternative to CLI flag.

### Non-Functional Requirements

- **NFR-1.1:** Each adapter module is <200 lines.
- **NFR-1.2:** Zero new required dependencies. Framework packages are optional extras only.
- **NFR-1.3:** Adapter overhead adds <10ms to each invocation.

---

## 2. Test Data Generation

### User Stories

- **TG-1:** As a user, I can run `agenteval generate --suite base.yaml --output expanded.yaml` to create edge-case variants of my test cases.
- **TG-2:** As a user, I can select which mutation strategies to apply via `--strategies empty,unicode,injection`.
- **TG-3:** As a user, I can use LLM-based generation for adversarial inputs via `--strategies llm`.
- **TG-4:** As a user, I can configure generation in my suite YAML under a `generate:` key.

### Functional Requirements

- **FR-2.1:** Built-in mutation strategies: `empty`, `max_length`, `unicode`, `sql_injection`, `prompt_injection`, `typos`, `negation`.
- **FR-2.2:** Each strategy takes an `EvalCase` and returns 1+ mutated `EvalCase` objects with modified input and appropriate `expected` (e.g., should not crash, should reject injection).
- **FR-2.3:** `llm` strategy sends existing cases to an LLM and asks for adversarial variants. Requires `OPENAI_API_KEY` or configurable endpoint.
- **FR-2.4:** Output YAML is valid and loadable by `agenteval run`.
- **FR-2.5:** Generated cases are tagged with `generated` and the strategy name (e.g., `generated:unicode`).
- **FR-2.6:** `--count <n>` limits total generated cases per original case (default: 3).
- **FR-2.7:** Deterministic strategies (empty, unicode, injection) produce identical output for same input (no randomness).

### Non-Functional Requirements

- **NFR-2.1:** Generation of 100 cases with deterministic strategies completes in <2 seconds.
- **NFR-2.2:** No new required dependencies. LLM strategy reuses existing httpx.

---

## 3. Performance Profiling

### User Stories

- **PP-1:** As a user, I can run `agenteval profile --run <id>` to see a per-case latency/cost breakdown.
- **PP-2:** As a user, I can see outlier cases flagged (>2σ from mean).
- **PP-3:** As a user, I can run `agenteval profile --trend --suite <name>` to see latency/cost trends across runs.
- **PP-4:** As a user, I get actionable recommendations ("Case X is 3x slower than average").

### Functional Requirements

- **FR-3.1:** `profile --run <id>` reads from SQLite store, displays table: case name, latency_ms, cost_usd, tokens_in, tokens_out.
- **FR-3.2:** Cases with latency >2σ above mean are flagged as outliers with ⚠️ marker.
- **FR-3.3:** `profile --trend --suite <name>` shows last N runs (default 10) with pass_rate, avg_latency, total_cost per run.
- **FR-3.4:** Recommendations are printed as actionable text: specific case names and suggested actions.
- **FR-3.5:** Output formats: `--format table` (default), `--format json`, `--format csv`.
- **FR-3.6:** Cost breakdown groups by grader type showing total cost per grader.

### Non-Functional Requirements

- **NFR-3.1:** Profile command runs in <1 second for runs with up to 1000 cases.
- **NFR-3.2:** No new dependencies. Uses stdlib statistics for σ calculation (no scipy required).

---

## 4. Distributed Runner

### User Stories

- **DR-1:** As a user, I can run `agenteval run suite.yaml --workers redis://localhost:6379` to distribute cases across workers.
- **DR-2:** As an ops person, I can start a worker with `agenteval worker --broker redis://localhost:6379`.
- **DR-3:** As a user, if no workers are available, the run falls back to local execution with a warning.
- **DR-4:** As a user, the final `EvalRun` looks identical whether run locally or distributed.

### Functional Requirements

- **FR-4.1:** Coordinator serializes `EvalCase` + agent config as JSON, pushes to Redis list `agenteval:tasks`.
- **FR-4.2:** Workers pop from `agenteval:tasks`, execute the case, push result to `agenteval:results:<run_id>`.
- **FR-4.3:** Coordinator polls `agenteval:results:<run_id>` until all cases complete or timeout.
- **FR-4.4:** Worker heartbeat: workers publish to `agenteval:workers` with TTL. Coordinator can list active workers.
- **FR-4.5:** If no results arrive within `--worker-timeout` (default 300s), coordinator falls back to local execution for remaining cases.
- **FR-4.6:** Results are merged into a single `EvalRun` with same schema as local runs.
- **FR-4.7:** Worker supports `--concurrency <n>` for parallel case execution (default: 1).
- **FR-4.8:** Agent callable must be importable by path (same as adapter `--agent` format). Workers import it at startup.

### Non-Functional Requirements

- **NFR-4.1:** Redis is the only supported broker. No abstraction layer for other backends.
- **NFR-4.2:** `redis` package is an optional extra: `pip install agentevalkit[distributed]`.
- **NFR-4.3:** Coordinator adds <50ms overhead per case vs local execution.
- **NFR-4.4:** Worker process is stateless; can be killed and restarted without data loss.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Framework APIs change frequently | Adapters break | Pin minimum versions, keep adapters thin, test against specific versions |
| LLM generation produces unusable cases | Wasted tokens/time | Preview mode (`--dry-run`), configurable prompts |
| Redis unavailability crashes distributed runs | User frustration | Graceful fallback to local, clear error messages |
| Scope creep on profiling (dashboards, charts) | Delays release | CLI text output only, defer visualization |
| Security of test generation (injection payloads) | Misuse | Cases are clearly tagged, warning in docs |

## Out of Scope

- Web UI or visualization
- Authentication/authorization for distributed workers
- Encrypted Redis connections (users configure Redis TLS themselves)
- Adapter auto-discovery (no plugin registry)
- Real-time streaming of results from workers
- Memory profiling (only latency and cost)
