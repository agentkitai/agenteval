# AgentEval v0.2.0 — Product Brief

**Author:** Paige (Product Strategist) | **Date:** 2026-02-13

## Strategic Context

AgentEval v0.1.0 shipped as a lightweight, local-first eval toolkit. The market has three tiers:

| Tier | Players | Weakness |
|------|---------|----------|
| Hosted platforms | Braintrust, LangSmith | Vendor lock-in, pricing, data leaves your machine |
| Heavy frameworks | DeepEval, Inspect AI | Complex setup, opinionated, large dependency trees |
| **Us** | **AgentEval** | **Missing CI story, limited graders** |

**Our wedge:** Developers who want `pytest` for agents — runs locally, fits in CI, no accounts, no dashboards. v0.2.0 doubles down on this by making AgentEval the obvious choice for "eval in CI."

## Why These 5 Features

1. **CI Integration** — This is the #1 request pattern. Without `agenteval ci`, people write wrapper scripts. Making CI native is table stakes for adoption.
2. **Advanced Graders** — json_schema and semantic cover 80% of uncovered grading needs. Latency/cost graders leverage data we already collect (AgentResult has these fields).
3. **AgentLens Import Polish** — Converts AgentLens users into AgentEval users. Currently half-baked; finishing it closes the "record → eval" loop.
4. **Parallel Execution** — Eval suites with 50+ cases are painfully slow sequential. The runner already uses asyncio; adding concurrency is natural.
5. **GitHub Actions Integration** — PR comments with eval results are the "wow" moment. Turns eval from a local chore into a visible team practice.

## What We're Killing / Descoping

- ❌ **No web UI / dashboard** — Terminal and CI output only
- ❌ **No hosted service** — Stays local/self-hosted forever
- ❌ **No TypeScript port** — Python only for v0.2.0
- ❌ **No custom embedding model support** — semantic grader uses one provider (sentence-transformers, optional dep)
- ❌ **No real-time streaming UI** — Progress bar yes, live dashboard no
- ❌ **No AgentLens write-back** — Import only, no exporting results back to AgentLens
- ❌ **No multi-turn eval** — Single input→output only (multi-turn is v0.3.0)

## Market Timing

- GitHub Actions is ubiquitous; every serious project has CI
- "Eval-driven development" is trending (Hamel Husain, Simon Willison pushing it)
- DeepEval just added CI features but requires their cloud; we can be the local alternative
- Window: ship before March 2026 while the narrative is hot

## Success Metrics

| Metric | Target |
|--------|--------|
| PyPI weekly downloads | 500+ (currently ~80) |
| GitHub stars | 200+ (currently ~40) |
| CI adoption | 10+ repos using `agenteval ci` in GitHub Actions |
| Test coverage | >90% across new code |
| Codebase size | 2800-3200 lines (controlled growth) |
