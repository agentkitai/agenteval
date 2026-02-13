# AgentEval v0.2.0 — Sprint Plan

**Author:** Bob (Sprint Planner) | **Date:** 2026-02-13

---

## Batch Overview

```
Batch 1: Advanced Graders        (no dependencies)
Batch 2: Parallel Execution      (no dependencies)
Batch 3: CI Integration          (depends on Batch 1 for full grader coverage in CI tests)
Batch 4: AgentLens Import Polish (no dependencies)
Batch 5: GitHub Actions          (depends on Batch 3 for CIResult model)
```

Each batch is independently committable and releasable.

---

## Batch 1: Advanced Graders

**Why first:** Zero dependencies, extends core capability, other features benefit from more graders.

### Stories

| Story | Description | Est. Lines | Est. Tests |
|-------|-------------|-----------|------------|
| B1-S1 | `json_schema` grader with inline schema + schema_file | ~45 | 8 |
| B1-S2 | `semantic` grader with optional sentence-transformers | ~60 | 8 |
| B1-S3 | `latency` grader | ~25 | 5 |
| B1-S4 | `cost` grader | ~25 | 5 |
| B1-S5 | Register all 4 in grader registry + update pyproject.toml extras | ~25 | 4 |

**Acceptance Criteria:**
- B1-S1: `json_schema` grader passes valid JSON, fails invalid, reports validation errors in reason. Handles both inline schema and file path.
- B1-S2: `semantic` grader computes cosine similarity, passes above threshold, fails below. Raises `ImportError` with helpful message when `sentence-transformers` missing.
- B1-S3: `latency` grader passes when `latency_ms ≤ max_ms`, score is proportional.
- B1-S4: `cost` grader passes when `cost_usd ≤ max_usd`, handles `None` cost gracefully (fail with reason).
- B1-S5: `get_grader("json_schema", ...)` etc. all work. `pyproject.toml` has `semantic` and `rich` extras.

**Total: ~180 lines, ~30 tests**

---

## Batch 2: Parallel Execution

**Why second:** Improves developer experience for all subsequent testing/dogfooding.

### Stories

| Story | Description | Est. Lines | Est. Tests |
|-------|-------------|-----------|------------|
| B2-S1 | `--parallel N` flag + semaphore-based concurrency in runner | ~80 | 6 |
| B2-S2 | `on_result` streaming callback in `run_suite` | ~20 | 3 |
| B2-S3 | Progress bar (rich + fallback) | ~60 | 4 |
| B2-S4 | Wire CLI: `--parallel` flag on `agenteval run`, progress bar integration | ~30 | 2 |

**Acceptance Criteria:**
- B2-S1: `run_suite(parallel=5)` runs 5 cases concurrently. Verify with timing test (5 slow cases finish in ~1x time, not 5x).
- B2-S2: `on_result` callback fires as each case completes. Results list maintains original case order.
- B2-S3: Progress bar shows `[N/total] case_name: ✓/✗`. Falls back gracefully without rich.
- B2-S4: `agenteval run suite.yaml --agent x --parallel 5` works end-to-end.

**Total: ~150 lines, ~15 tests**

---

## Batch 3: CI Integration

**Why third:** Builds on graders (Batch 1) for comprehensive CI testing. Core value proposition of v0.2.0.

### Stories

| Story | Description | Est. Lines | Est. Tests |
|-------|-------------|-----------|------------|
| B3-S1 | `CIConfig` + `CIResult` models, `check_thresholds()` function | ~60 | 6 |
| B3-S2 | Regression detection (compare against baseline run) | ~50 | 5 |
| B3-S3 | JSON formatter | ~40 | 4 |
| B3-S4 | JUnit XML formatter | ~60 | 5 |
| B3-S5 | `agenteval ci` CLI command wiring | ~50 | 5 |

**Acceptance Criteria:**
- B3-S1: `check_thresholds()` returns `CIResult(passed=False)` when pass rate < min. Returns `passed=True` when all thresholds met.
- B3-S2: Given baseline run where case X passed, if current run case X fails, it's listed as regression. Regression % calculated correctly.
- B3-S3: JSON output is valid JSON, contains `passed`, `summary`, `results` keys. Validated against a JSON schema in test.
- B3-S4: JUnit XML is well-formed, has one `<testcase>` per case, failures have `<failure>` elements. Validated against JUnit XSD in test.
- B3-S5: `agenteval ci suite.yaml --agent x --min-pass-rate 0.5` exits 0 when pass rate ≥ 50%. Exits 1 when below.

**Total: ~260 lines, ~25 tests**

---

## Batch 4: AgentLens Import Polish

**Why fourth:** Independent feature, can be developed in parallel with Batch 3 if two developers available.

### Stories

| Story | Description | Est. Lines | Est. Tests |
|-------|-------------|-----------|------------|
| B4-S1 | Refactor existing importer: clean API, `AgentLensClient` class | ~80 | 5 |
| B4-S2 | `AssertionGenerator`: tool_calls → tool_check, output → contains | ~60 | 6 |
| B4-S3 | `InteractiveReviewer`: terminal-based case review | ~50 | 4 |
| B4-S4 | Batch import: `--batch --filter` with session listing | ~40 | 3 |
| B4-S5 | CLI command: `agenteval import agentlens` with all flags | ~40 | 2 |

**Acceptance Criteria:**
- B4-S1: `AgentLensClient.fetch_session(id)` returns structured session data. Existing tests still pass.
- B4-S2: Given a session with 3 tool calls, generates 3 `tool_check` assertions. Given output text, generates `contains` assertion with extracted key phrases.
- B4-S3: Interactive mode shows each case, accepts y/n/e(dit). Edit opens case in `$EDITOR` or inline prompt. Skipped cases excluded from output.
- B4-S4: `--batch --filter "tag:prod"` fetches matching session IDs and imports all. Output is single YAML suite.
- B4-S5: Full CLI round-trip: import → save YAML → `agenteval run` on saved file succeeds.

**Total: ~270 lines, ~20 tests**

---

## Batch 5: GitHub Actions Integration

**Why last:** Depends on CI (Batch 3) for `CIResult`. Highest "nice to have" vs "must have" ratio.

### Stories

| Story | Description | Est. Lines | Est. Tests |
|-------|-------------|-----------|------------|
| B5-S1 | `GitHubClient`: PR comment posting via urllib | ~70 | 5 |
| B5-S2 | Comment formatting: markdown table + summary | ~40 | 4 |
| B5-S3 | Comment update (find existing by marker, PATCH) | ~30 | 3 |
| B5-S4 | Badge SVG generation | ~40 | 3 |
| B5-S5 | CLI commands: `github-comment`, `badge` | ~30 | 2 |
| B5-S6 | Example workflow YAML + docs | ~40 (YAML/docs) | 0 |

**Acceptance Criteria:**
- B5-S1: Given `GITHUB_TOKEN` and `GITHUB_EVENT_PATH`, posts comment to correct PR. Test with mocked urllib.
- B5-S2: Comment contains markdown table with columns: Case, Status (✓/✗), Score, Latency. Has summary line with overall pass rate.
- B5-S3: Second run updates existing comment (identified by `<!-- agenteval -->` marker) instead of creating duplicate.
- B5-S4: `generate_badge(0.95, "badge.svg")` creates valid SVG. Color: green ≥90%, yellow ≥70%, red <70%.
- B5-S5: `agenteval github-comment --run <id>` works. `agenteval badge --run <id> --output badge.svg` works.
- B5-S6: `examples/agenteval.yml` is a working GitHub Actions workflow.

**Total: ~210 lines, ~17 tests**

---

## Summary

| Batch | Feature | New Lines | New Tests | Depends On |
|-------|---------|-----------|-----------|------------|
| 1 | Advanced Graders | ~180 | ~30 | — |
| 2 | Parallel Execution | ~150 | ~15 | — |
| 3 | CI Integration | ~260 | ~25 | Batch 1 (soft) |
| 4 | AgentLens Import | ~270 | ~20 | — |
| 5 | GitHub Actions | ~210 | ~17 | Batch 3 |
| **Total** | | **~1070** | **~107** | |

**Projected v0.2.0 totals:** ~2720 source lines, ~234 tests.

**Estimated timeline:** 5 batches × 1-2 days each = 1-2 weeks of focused work.
