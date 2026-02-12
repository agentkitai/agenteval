# AgentEval 🧪

[![PyPI](https://img.shields.io/pypi/v/agentevalkit)](https://pypi.org/project/agentevalkit/)
[![Tests](https://img.shields.io/badge/tests-127%20passing-brightgreen)]()
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Testing and evaluation framework for AI agents.** Define test suites in YAML, grade agent outputs with 6 pluggable graders, track results over time, and detect regressions with statistical comparison.

---

## Why AgentEval?

AI agents are **hard to test**. They're non-deterministic, they call tools, and their outputs vary between runs. Traditional unit tests don't cut it.

- 🎯 **YAML-based test suites** — Define inputs, expected outputs, and grading criteria declaratively
- 📊 **Statistical regression detection** — Welch's t-test across multiple runs, not just pass/fail
- 🔌 **6 built-in graders** — Exact match, contains, regex, tool-check, LLM-judge, and custom
- 🔗 **AgentLens integration** — Import real production sessions as test cases
- 💰 **Cost & latency tracking** — Know what each eval costs in tokens and dollars
- 🗄️ **SQLite result storage** — Every run is persisted for historical comparison

---

## Quick Start

```bash
pip install agentevalkit
```

### 1. Define a test suite

```yaml
# suite.yaml
name: my-agent-tests
agent: my_agent:run

cases:
  - name: basic-math
    input: "What is 2 + 2?"
    expected:
      output_contains: ["4"]
    grader: contains

  - name: tool-usage
    input: "Search for the weather in NYC"
    expected:
      tools_called: ["web_search"]
    grader: tool-check

  - name: format-check
    input: "List 3 colors"
    expected:
      pattern: "\\d\\.\\s+\\w+"
    grader: regex
```

### 2. Create your agent callable

```python
# my_agent.py
from agenteval.models import AgentResult

def run(input_text: str) -> AgentResult:
    # Your agent logic here
    return AgentResult(
        output="The answer is 4.",
        tools_called=[{"name": "web_search", "args": {"query": "weather NYC"}}],
        tokens_in=12,
        tokens_out=8,
        cost_usd=0.0003,
    )
```

### 3. Run the eval

```
$ agenteval run --suite suite.yaml --verbose

============================================================
Suite: my-agent-tests  |  Run: c1c6493118d5
============================================================
  PASS  basic-addition (score=1.00, 150ms)
  PASS  capital-city (score=1.00, 200ms)
  PASS  quantum-summary (score=1.00, 350ms)
  PASS  tool-usage (score=1.00, 280ms)
  PASS  list-format (score=1.00, 120ms)

Total: 5  Passed: 5  Failed: 0  Pass rate: 100%
Cost: $0.0023  Avg latency: 220ms
```

---

## Features

### 🎯 6 Built-in Graders

| Grader | What it checks | Expected fields |
|--------|---------------|----------------|
| `exact` | Exact string match | `output` |
| `contains` | Substring presence | `output_contains: [list]` |
| `regex` | Pattern matching | `pattern` |
| `tool-check` | Tools were called | `tools_called: [list]` |
| `llm-judge` | LLM evaluates quality | `criteria` (free-form) |
| `custom` | Your own function | `grader_config: {function: "mod:fn"}` |

### 📊 Statistical Comparison

Compare runs with Welch's t-test to detect statistically significant regressions:

```
$ agenteval compare c1c6493118d5,d17a2dce0222 4ee7e40601e3,ba5b0dde212b

============================================================================
Comparing: c1c6493118d5,d17a2dce0222 vs 4ee7e40601e3,ba5b0dde212b
Alpha: 0.05  Regression threshold: 0.0
============================================================================

Case                          Base   Target     Diff   p-value  Sig Status
----------------------------------------------------------------------------
  basic-addition             1.000    1.000   +0.000         —
  capital-city               1.000    0.500   -0.500    0.4533
  quantum-summary            1.000    0.500   -0.500    0.4533
  tool-usage                 1.000    0.000   -1.000    0.0000    * ▼ regressed
  list-format                1.000    0.500   -0.500    0.4533

Summary: 0 improved, 1 regressed, 4 unchanged

⚠ 1 regression(s) detected!
```

Run the same suite multiple times and compare groups: `agenteval compare RUN_A1,RUN_A2 vs RUN_B1,RUN_B2`. Uses scipy when available, falls back to pure Python.

### 🔗 AgentLens Integration

Import real agent sessions from [AgentLens](https://github.com/amitpaz/agentlens) as test suites:

```bash
agenteval import --from agentlens --db sessions.db --output suite.yaml --grader contains
# Imported 42 cases → suite.yaml
```

Turn production traffic into regression tests — no manual test writing needed.

### 💰 Cost & Latency Tracking

Every eval tracks tokens and cost. Your agent callable returns `AgentResult` with `tokens_in`, `tokens_out`, and `cost_usd`, and AgentEval aggregates them per run.

---

## YAML Suite Format

Full annotated example:

```yaml
name: my-agent-tests           # Suite name (shown in reports)
agent: my_module:my_agent      # Default agent callable (module:function)

defaults:                       # Defaults applied to all cases
  grader: contains
  grader_config:
    ignore_case: true

cases:
  - name: basic-math            # Unique case name
    input: "What is 2 + 2?"     # Input passed to agent
    expected:                    # Grader-specific expected values
      output_contains: ["4"]
    grader: contains             # Override default grader
    tags: [math, basic]          # Tags for filtering (--tag math)

  - name: tool-usage
    input: "Search for weather"
    expected:
      tools_called: ["web_search"]
    grader: tool-check

  - name: quality-check
    input: "Explain gravity"
    expected:
      criteria: "Should mention Newton or Einstein, be scientifically accurate"
    grader: llm-judge
    grader_config:
      model: gpt-4o-mini         # LLM judge model
      api_base: https://api.openai.com/v1

  - name: custom-validation
    input: "Generate a JSON object"
    expected: {}
    grader: custom
    grader_config:
      function: my_graders:validate_json  # Your grader function
```

---

## CLI Reference

### `agenteval run`

```bash
agenteval run --suite suite.yaml [--agent module:fn] [--verbose] [--tag math] [--timeout 30] [--db agenteval.db]
```

- `--suite` — Path to YAML suite file (required)
- `--agent` — Override the agent callable from the suite
- `--verbose` / `-v` — Show per-case pass/fail details
- `--tag` — Filter cases by tag (repeatable)
- `--timeout` — Per-case timeout in seconds (default: 30)
- `--db` — SQLite database path (default: `agenteval.db`)

Exit code is 1 if any case fails.

### `agenteval list`

```bash
agenteval list [--suite-filter name] [--limit 20] [--db agenteval.db]
```

```
$ agenteval list --limit 5

ID             Suite                Passed   Failed   Rate     Created
--------------------------------------------------------------------------------
aeccd5e53f03   math-agent-demo      2        3        40%      2026-02-12T21:12:12
4f3e380f622c   math-agent-demo      3        2        60%      2026-02-12T21:12:12
bd4ef3a0727b   math-agent-demo      1        4        20%      2026-02-12T21:12:12
e2ca43e99852   math-agent-demo      3        2        60%      2026-02-12T21:12:11
32ed650cab6d   math-agent-demo      2        3        40%      2026-02-12T21:12:11
```

### `agenteval compare`

```bash
agenteval compare RUN_A RUN_B [--alpha 0.05] [--threshold 0.0] [--stats/--no-stats]
agenteval compare RUN_A1,RUN_A2 vs RUN_B1,RUN_B2   # Multi-run comparison
```

### `agenteval import`

```bash
agenteval import --from agentlens --db sessions.db --output suite.yaml [--grader contains] [--limit 100]
```

---

## Grader Reference

### `exact`
Compares `result.output` exactly with `expected.output`. Config: `ignore_case: bool`.

```yaml
expected:
  output: "The answer is 42."
grader: exact
grader_config:
  ignore_case: true
```

### `contains`
Checks that all substrings in `expected.output_contains` appear in the output.

```yaml
expected:
  output_contains: ["Paris", "France"]
grader: contains
```

### `regex`
Matches `result.output` against `expected.pattern` (Python regex). Config: `flags: [IGNORECASE, DOTALL, MULTILINE]`.

```yaml
expected:
  pattern: "\\d+\\.\\d+"
grader: regex
grader_config:
  flags: [IGNORECASE]
```

### `tool-check`
Verifies expected tools were called. Config: `ordered: bool` for sequence matching.

```yaml
expected:
  tools_called: ["web_search", "calculator"]
grader: tool-check
grader_config:
  ordered: true
```

### `llm-judge`
Sends the input, output, and criteria to an LLM for evaluation. Requires `OPENAI_API_KEY` or compatible API.

```yaml
expected:
  criteria: "Response should be helpful, accurate, and concise"
grader: llm-judge
grader_config:
  model: gpt-4o-mini
```

### `custom`
Imports and calls your own grader function. Must accept `(case: EvalCase, result: AgentResult) -> GradeResult`.

```yaml
grader: custom
grader_config:
  function: my_module:my_grader
```

---

## Part of the AgentKit Ecosystem

AgentEval works great standalone, and even better with:

- **[AgentLens](https://github.com/amitpaz/agentlens)** — Session recording & observability for AI agents
- **[Lore](https://github.com/amitpaz/lore)** — Prompt management and versioning
- **[AgentGate](https://github.com/amitpaz/agentgate)** — API gateway for AI agents
- **[FormBridge](https://github.com/amitpaz/formbridge)** — Form automation with AI

---

## Contributing

Contributions welcome! This project uses:

- **pytest** for testing (127 tests passing)
- **ruff** for linting
- **src layout** (`src/agenteval/`)

```bash
git clone https://github.com/amitpaz1/agenteval.git
cd agenteval
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
