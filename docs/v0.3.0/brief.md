# AgentEval v0.3.0 — Product Brief

**Author:** Paige (Product) | **Date:** 2026-02-13

## Strategic Context

AgentEval v0.2.0 is a solid eval toolkit: YAML suites, 10 graders, CI integration, parallel runner. But users still face three friction points:

1. **Wiring pain** — Every framework (LangChain, CrewAI, AutoGen) needs a custom callable. This is the #1 barrier to adoption.
2. **Test coverage gaps** — Users write happy-path cases and miss edge cases. No tooling helps them think adversarially.
3. **No performance insight** — Latency/cost data is captured but not analyzed. Users can't answer "is my agent getting slower?"
4. **Scale ceiling** — Large suites (500+ cases) take too long on a single machine.

v0.3.0 removes these barriers in order of impact.

## Why These 4, Why Now

| Feature | Impact | Effort | Priority |
|---------|--------|--------|----------|
| Framework Adapters | Unlocks 80% of potential users | Low (thin wrappers) | P0 |
| Test Data Generation | Unique differentiator, no competitor does this | Medium | P1 |
| Performance Profiling | Low-hanging fruit, data already exists | Low | P1 |
| Distributed Runner | Enables enterprise scale | Medium | P2 |

**Market timing:** LangChain has 80k+ GitHub stars but no built-in eval. CrewAI and AutoGen are growing fast. First-mover on native adapter support = default eval tool for these ecosystems.

## What We're NOT Building

- **UI/Dashboard** — CLI-first. Web UI is v0.4.0+ territory.
- **Custom broker backends** — Redis only. No RabbitMQ, no SQS, no Kafka.
- **Agent-specific graders** — Adapters extract data; existing graders evaluate it.
- **Hosted service** — This is a library, not a platform.
- **Auto-fix/auto-tune** — Profiling recommends, it doesn't act.
- **Streaming support in adapters** — Adapters wait for complete response. Streaming is a future concern.

## Success Metrics

| Metric | Target |
|--------|--------|
| Framework adapter adoption | 30% of new users use an adapter within 30 days |
| Test generation usage | Users who run `generate` create 3x more test cases |
| Profile command usage | 20% of users run `profile` at least once |
| Distributed runner | Successfully runs 1000-case suite across 5 workers |
| New dependencies added to core | 0 (all optional extras) |

## Differentiation

No existing tool offers: eval framework + framework adapters + adversarial test generation + distributed execution. Competitors (promptfoo, deepeval) focus on prompt testing, not agent testing. AgentEval owns the agent-specific niche.
