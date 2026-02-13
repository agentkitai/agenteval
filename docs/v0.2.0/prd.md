# AgentEval v0.2.0 — Product Requirements Document

**Author:** John (Product Manager) | **Date:** 2026-02-13

---

## User Stories

### Feature 1: CI Integration

- **US-CI-1:** As a developer, I can run `agenteval ci suite.yaml --agent my_agent` and get exit code 0 (pass) or 1 (fail) based on configurable thresholds.
- **US-CI-2:** As a CI engineer, I can set `--min-pass-rate 0.95` and `--max-regression 5` to define failure criteria.
- **US-CI-3:** As a CI engineer, I can get JSON output (`--format json`) for machine parsing.
- **US-CI-4:** As a CI engineer, I can get JUnit XML output (`--format junit`) for integration with CI dashboards.
- **US-CI-5:** As a developer, I can compare against a baseline run (`--baseline <run_id>`) to detect regressions per-case.

### Feature 2: Advanced Graders

- **US-GR-1:** As a developer, I can use `grader: json_schema` with a JSON Schema to validate structured agent output.
- **US-GR-2:** As a developer, I can use `grader: semantic` with a similarity threshold to grade on meaning rather than exact text.
- **US-GR-3:** As a developer, I can use `grader: latency` with `max_ms` to fail cases that are too slow.
- **US-GR-4:** As a developer, I can use `grader: cost` with `max_usd` to fail cases that cost too much.

### Feature 3: AgentLens Import Polish

- **US-AL-1:** As a developer, I can run `agenteval import agentlens --session <id> --server <url>` to import a session as eval cases.
- **US-AL-2:** As a developer, I can run `agenteval import agentlens --batch --filter "tag:production"` to import multiple sessions.
- **US-AL-3:** As a developer, I can use `--interactive` to review and edit generated cases before saving.
- **US-AL-4:** As a developer, the importer auto-generates appropriate assertions (tool_check for tool calls, contains for outputs).

### Feature 4: Parallel Execution

- **US-PE-1:** As a developer, I can run `agenteval run --parallel 5` to execute 5 cases concurrently.
- **US-PE-2:** As a developer, I see a progress bar showing completed/total cases.
- **US-PE-3:** As a developer, each case respects its timeout independently.
- **US-PE-4:** As a developer, results print as they complete (streaming output).

### Feature 5: GitHub Actions Integration

- **US-GH-1:** As a developer, I can run `agenteval github-comment --run <id>` in CI to post a PR comment with results.
- **US-GH-2:** As a developer, the PR comment shows a markdown table with pass/fail per case and overall stats.
- **US-GH-3:** As a developer, I can generate a status badge SVG with `agenteval badge --run <id>`.
- **US-GH-4:** As a developer, I can copy a reusable workflow template from the docs/repo.

---

## Functional Requirements

### CI Integration
- **FR-CI-1:** `agenteval ci` accepts suite path, agent reference, `--min-pass-rate` (float, default 1.0), `--max-regression` (float %, default 0).
- **FR-CI-2:** Exit code 0 if all thresholds met, 1 if any threshold violated.
- **FR-CI-3:** `--format json` outputs `{"passed": bool, "summary": {...}, "results": [...]}` to stdout.
- **FR-CI-4:** `--format junit` outputs valid JUnit XML (one `<testcase>` per eval case).
- **FR-CI-5:** `--baseline <run_id>` loads a previous run from the store and computes per-case regression.
- **FR-CI-6:** Regression = case that passed in baseline but fails now. Regression % = regressions / total.

### Advanced Graders
- **FR-GR-1:** `json_schema` grader accepts `schema` (inline dict) or `schema_file` (path) in grader_config. Uses `jsonschema` library (required dep).
- **FR-GR-2:** `json_schema` grader: score=1.0 if valid, score=0.0 if invalid. Reason includes validation error message.
- **FR-GR-3:** `semantic` grader accepts `threshold` (float, default 0.8) and `model` (string, default "all-MiniLM-L6-v2"). Uses `sentence-transformers` (optional dep).
- **FR-GR-4:** `semantic` grader: score = cosine similarity. Passed = score ≥ threshold.
- **FR-GR-5:** `semantic` grader raises clear error if sentence-transformers not installed.
- **FR-GR-6:** `latency` grader accepts `max_ms` (int). Passed = agent_result.latency_ms ≤ max_ms. Score = max(0, 1 - latency/max_ms).
- **FR-GR-7:** `cost` grader accepts `max_usd` (float). Passed = agent_result.cost_usd ≤ max_usd. Score = max(0, 1 - cost/max_usd).

### AgentLens Import
- **FR-AL-1:** CLI command `agenteval import agentlens` with `--session`, `--server` (default http://localhost:3000), `--output` (default stdout YAML).
- **FR-AL-2:** Auto-assertion: tool calls in session → `tool_check` assertions. Final output → `contains` assertion with key phrases.
- **FR-AL-3:** `--interactive` opens a case-by-case review: show generated case, prompt y/n/edit for each.
- **FR-AL-4:** `--batch --filter <query>` fetches sessions matching filter from AgentLens API, imports all.
- **FR-AL-5:** Output is valid AgentEval YAML suite format, loadable by `agenteval run`.

### Parallel Execution
- **FR-PE-1:** `--parallel N` on `agenteval run` sets concurrency. Default N=1 (sequential, backward compatible).
- **FR-PE-2:** Implementation uses `asyncio.Semaphore(N)` wrapping existing `_run_case`.
- **FR-PE-3:** Progress bar uses `rich` if available, falls back to simple `[3/10]` line output.
- **FR-PE-4:** Per-case timeout is enforced independently (already exists in `_call_agent`).
- **FR-PE-5:** Results are collected in original case order for deterministic output, but printed as they complete.

### GitHub Actions
- **FR-GH-1:** `agenteval github-comment` reads `GITHUB_TOKEN` env var and PR context from `GITHUB_EVENT_PATH`.
- **FR-GH-2:** Posts/updates a comment (uses marker comment to find existing) via GitHub REST API.
- **FR-GH-3:** Comment body: markdown table (case, status, score, latency) + summary line.
- **FR-GH-4:** `agenteval badge` generates an SVG badge file (pass rate %) using a simple template (no external service).
- **FR-GH-5:** Reusable workflow YAML template included in `examples/` directory.

---

## Non-Functional Requirements

- **NFR-1:** All new features have ≥90% test coverage.
- **NFR-2:** No new required dependencies. `jsonschema` becomes required; `sentence-transformers` and `rich` are optional.
- **NFR-3:** CLI commands complete in <100ms overhead (excluding agent calls).
- **NFR-4:** Parallel execution with N=10 handles 100 cases without memory issues.
- **NFR-5:** All output formats (JSON, JUnit XML, YAML) are validated against schemas in tests.
- **NFR-6:** Backward compatible — all v0.1.0 suites and commands work unchanged.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| sentence-transformers is 500MB+ | Users won't install it | Make it optional; clear error message; document lightweight alternatives |
| GitHub API rate limits | PR comments fail in busy repos | Retry with backoff; degrade gracefully (print to stdout if API fails) |
| AgentLens API changes | Import breaks | Version the API client; pin to known AgentLens version in docs |
| Parallel execution race conditions | Flaky results | Semaphore-based (no shared mutable state); results collected via asyncio.gather |
| JUnit XML format variations | CI systems reject output | Test against Jenkins, GitHub Actions, CircleCI expected formats |

---

## Out of Scope (Explicit)

- Web UI or dashboard of any kind
- Hosted/cloud eval service
- Multi-turn conversation evaluation
- Custom embedding model endpoints (only sentence-transformers)
- AgentLens write-back (exporting results to AgentLens)
- TypeScript/JavaScript SDK
- Eval case generation from production logs (beyond AgentLens)
- Authentication for AgentLens (assumes local/unauthenticated)
