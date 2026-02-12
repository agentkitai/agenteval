# AgentEval — Product Requirements Document

**Author:** John (Product Manager)  
**Date:** 2026-02-12  
**Status:** Draft — MVP Only

## What Makes Agent Evals Different

Before user stories, let's be clear about why this isn't "just another eval tool":

| Prompt Evals | Agent Evals |
|-------------|-------------|
| Single input → single output | Multi-step trajectories |
| Text comparison | Tool selection + argument correctness |
| Deterministic enough for exact match | Non-deterministic, needs statistical comparison |
| Cheap to run | Expensive (multiple LLM calls per case) |
| One grading dimension | Multiple: did it use the right tools? In the right order? Get the right answer? At what cost? |

## MVP User Stories

Ruthlessly scoped. Each story must be useful on its own.

### S1: Define Eval Cases in YAML
**As** an agent developer, **I want** to define test cases in a YAML file **so that** I can version-control my evals alongside my code.

```yaml
# evals/booking-agent.yaml
suite: booking-agent
cases:
  - name: simple-flight-booking
    input: "Book me a flight from SFO to JFK on March 15"
    expected:
      tools_called: ["search_flights", "book_flight"]
      output_contains: "confirmation"
    grader: llm-judge
    grader_config:
      criteria: "Agent found flights and completed booking"
```

**Acceptance:** Can load, validate, and list eval suites from YAML files.

### S2: Run Evals via CLI
**As** an agent developer, **I want** to run `agenteval run evals/booking-agent.yaml` **so that** I get pass/fail results for each case.

The agent is provided as a Python callable:
```python
# agent.py
async def my_agent(input: str) -> AgentResult:
    ...
```

Config in the YAML points to the callable:
```yaml
agent: agent:my_agent
```

**Acceptance:** CLI runs all cases, shows pass/fail per case, returns exit code 0/1.

### S3: Multiple Grader Types
**As** an agent developer, **I want** different grading strategies **so that** I can pick the right one for each case.

MVP graders:
- **exact** — output matches expected string
- **contains** — output contains substring(s)
- **regex** — output matches pattern
- **tool-check** — specific tools were called (in any order or exact order)
- **llm-judge** — LLM grades the output against criteria
- **custom** — user provides a Python function

**Acceptance:** All 6 graders work. Custom grader loads from user's module.

### S4: Compare Two Runs
**As** an agent developer, **I want** to run `agenteval compare run-123 run-456` **so that** I can see if my changes made things better or worse.

Shows:
- Per-case diff (pass→fail, fail→pass, score change)
- Aggregate: overall pass rate change
- Cost comparison (total tokens/cost per run)
- Statistical significance for score-based graders (Welch's t-test when N>1 per case)

**Acceptance:** Compare command works, shows clear diff output.

### S5: Cost Tracking
**As** an agent developer, **I want** to see how much each eval run costs **so that** I can make cost/quality tradeoffs.

Track per-case: input tokens, output tokens, total cost (if model pricing available), latency.

**Acceptance:** Cost summary shown after each run and in compare output.

### S6: Import from AgentLens (Optional)
**As** an AgentLens user, **I want** to import captured sessions as eval cases **so that** my tests reflect real usage.

`agenteval import-sessions sessions.json --output evals/from-prod.yaml`

Takes AgentLens JSON export, creates eval cases with the original input and a human-reviewable expected output.

**Acceptance:** Import command produces valid YAML eval suite. Works with AgentLens JSON export format.

## Deferred (NOT MVP)

- UI dashboard
- Hosted/remote eval runners
- Dataset management / versioning
- CI/CD integrations (GitHub Actions, etc.)
- Parallel eval execution
- TypeScript SDK
- MCP agent interface (start with callable only)
- HTTP agent interface
- Eval case generation from descriptions
- Fine-tuning based on eval results

## Non-Functional Requirements

- Python 3.10+
- < 3 dependencies beyond stdlib (httpx, pyyaml, click)
- SQLite for result storage, no migrations
- Runs offline (except LLM calls for the agent and llm-judge grader)
- MIT license
