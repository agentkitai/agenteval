# AgentEval — Product Brief

**Author:** Paige (Product Strategist)  
**Date:** 2026-02-12  
**Status:** Draft

## Problem

Agent developers have no reliable way to test their agents. The current state:

1. **Manual vibes-checking** — run the agent, eyeball the output, ship it
2. **Prompt evals don't cover agents** — existing eval tools test prompt→response. Agents do multi-step workflows with tool calls, branching logic, and non-deterministic behavior. Prompt evals miss all of this.
3. **No regression detection** — you change a system prompt or swap models, and you have no idea what broke until users complain
4. **Cost blindness** — agents are expensive. Nobody tracks cost-per-eval to know if a "better" config is 3x more expensive.

This is the gap between "I built an agent" and "I ship an agent to production with confidence."

## Who Is This For?

**Primary:** Solo devs and small teams building AI agents in Python who want to test before shipping.

**Not for:** Enterprise ML teams with custom infra, academic researchers benchmarking foundation models, prompt engineers who aren't building agents.

## Market Landscape — Honest Assessment

| Tool | What It Does | Agent Eval Support | OSS? |
|------|-------------|-------------------|------|
| **Braintrust** | Full eval platform, logging, datasets | Good — supports multi-step, tool use | No (proprietary SaaS) |
| **LangSmith Evals** | LangChain's eval suite | Decent — tied to LangChain ecosystem | No |
| **Promptfoo** | CLI-based prompt/model eval | Prompt-focused, limited agent support | Yes (MIT) |
| **DeepEval** | Python eval framework | Growing agent support, pytest-style | Yes (Apache 2.0) |
| **Ragas** | RAG-focused evals | RAG only, not general agents | Yes |
| **Inspect AI** | UK AISI's agent eval framework | Strong agent support, tasks-based | Yes |

**Honest take:** This market is getting crowded. Braintrust and DeepEval are strong. Inspect AI is well-designed for agent evals specifically.

**What's NOT covered well:**
- Importing real production sessions as test cases (everyone starts from synthetic data)
- Local-first with zero cloud dependency
- Framework-agnostic agent interface (most tools assume LangChain or their own framework)
- Statistical run comparison with cost tracking

## Unique Angle

1. **Real sessions → test cases.** AgentLens captures production sessions. AgentEval imports them as eval cases. Your tests come from reality, not imagination.
2. **Local-first, zero cloud.** `pip install agenteval`, SQLite, done. No accounts, no API keys (except for your agent's own LLM).
3. **Agent-native, not prompt-native.** First-class support for tool call evaluation, trajectory comparison, multi-step grading.
4. **AgentKit ecosystem.** Works standalone, but integrates naturally with Lore, AgentLens, AgentGate.

## Business Model

Open-core (MIT license):
- **Free:** CLI, all graders, local runs, SQLite storage
- **Cloud (later, maybe):** Team dashboards, shared eval results, CI/CD integration, hosted runs

**Reality check:** The cloud tier is speculative. Don't build for it. Build a great CLI tool first.

## Market Timing: 5/10

**Why not higher:**
- Competitors exist and are well-funded (Braintrust has $36M+)
- DeepEval is OSS and has momentum
- The "agent eval" category is still forming — unclear if it becomes its own thing or gets absorbed into existing tools

**Why not lower:**
- Agent adoption is exploding, testing is genuinely painful
- The AgentLens integration angle is unique and real
- Local-first OSS still has a lane (see: Lore's traction)

## KILLED From Scope

- ❌ Hosted eval runners
- ❌ Dataset marketplace
- ❌ Model fine-tuning
- ❌ UI dashboard (CLI only for MVP)
- ❌ TypeScript SDK (Python first)
- ❌ Benchmarking against public datasets
- ❌ Custom model hosting
- ❌ Multi-tenant anything
