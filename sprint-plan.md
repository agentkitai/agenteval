# AgentEval — Sprint Plan (Phase 1: MVP)

**Author:** Bob (Sprint Planner)  
**Date:** 2026-02-12  
**Target:** `pip install agenteval` with working CLI

## Batch 1: Foundation (8h)

**Stories:** Core models + YAML loader + project scaffold

- [ ] Project setup: pyproject.toml, package structure, dev deps (pytest, ruff)
- [ ] `models.py` — EvalSuite, EvalCase, EvalRun, EvalResult, AgentResult, GradeResult dataclasses
- [ ] `loader.py` — Load and validate YAML eval suites
- [ ] Tests: model creation, YAML loading, validation errors

**Deliverable:** Can load eval suites from YAML. `import agenteval` works.

## Batch 2: Graders (8h)

**Stories:** S3 — All 6 grader types

- [ ] Grader protocol + base class
- [ ] ExactGrader, ContainsGrader, RegexGrader
- [ ] ToolCheckGrader (ordered + unordered modes)
- [ ] LLMJudgeGrader (uses httpx to call OpenAI-compatible API)
- [ ] CustomGrader (import user function by dotted path)
- [ ] Tests: each grader with pass/fail cases. LLM judge mocked.

**Deliverable:** All graders work in isolation.

## Batch 3: Runner + SQLite (8h)

**Stories:** S2 (partial), S5 — Execute evals and store results

- [ ] `store.py` — SQLite init, save run, save results, query runs
- [ ] `runner.py` — Load suite, import agent callable, run cases sequentially, grade, store
- [ ] Cost/token tracking in results
- [ ] Tests: end-to-end run with mock agent, results persisted

**Deliverable:** Can programmatically run an eval suite and get results.

## Batch 4: CLI (6h)

**Stories:** S2 (complete) — CLI interface

- [ ] `cli.py` — Click commands: `run`, `list`
- [ ] `agenteval run suite.yaml` — runs evals, prints table, exit code
- [ ] `agenteval list` — shows past runs with summary
- [ ] Terminal output formatting (pass/fail colors, summary table)
- [ ] Tests: CLI integration tests

**Deliverable:** `agenteval run` works end-to-end from terminal.

## Batch 5: Compare (6h)

**Stories:** S4 — Run comparison

- [ ] `compare.py` — Load two runs, compute diffs
- [ ] Per-case: pass→fail, fail→pass, score delta
- [ ] Aggregate: pass rate change, cost change
- [ ] Statistical significance (Welch's t-test, optional scipy)
- [ ] `agenteval compare <id1> <id2>` CLI command
- [ ] Tests: comparison with known data

**Deliverable:** Can compare two runs and see regressions.

## Batch 6: AgentLens Import + Polish (4h)

**Stories:** S6 — Import sessions

- [ ] `importers/agentlens.py` — Read AgentLens JSON, output YAML suite
- [ ] `agenteval import-sessions` CLI command
- [ ] README.md with quickstart
- [ ] `pip install agenteval` works (test in clean venv)
- [ ] Tests: import with sample data

**Deliverable:** Complete MVP. Publishable to PyPI.

---

## Summary

| Batch | Hours | Cumulative |
|-------|-------|------------|
| 1: Foundation | 8h | 8h |
| 2: Graders | 8h | 16h |
| 3: Runner + SQLite | 8h | 24h |
| 4: CLI | 6h | 30h |
| 5: Compare | 6h | 36h |
| 6: Import + Polish | 4h | 40h |

**Total: ~40 hours** (one solid week of focused work)

## Risks

- **LLM Judge grader** is the hardest part — prompt engineering for reliable grading. Budget extra time here.
- **Agent callable interface** needs clear docs or people won't know how to wrap their agent. Good examples > good code.
- **Scope creep** — the temptation to add parallel execution, pretty output, CI integration. Resist. Ship the 40h version first.
