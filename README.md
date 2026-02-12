# AgentEval

[![PyPI](https://img.shields.io/pypi/v/agenteval)](https://pypi.org/project/agenteval/)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)]()

**Testing and evaluation framework for AI agents.** Define test suites in YAML, grade agent outputs with pluggable graders, track results over time, and detect regressions with statistical comparison.

## Quick Start

```bash
pip install agenteval
```

### 1. Define a test suite (`suite.yaml`)

```yaml
name: my-agent-tests
agent: my_agent:run

cases:
  - name: basic-math
    input: "What is 2 + 2?"
    expected:
      output: "4"
    grader: contains

  - name: tool-usage
    input: "Search for the weather in NYC"
    expected:
      tools: ["web_search"]
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
        output="4",
        tools_called=[],
        tokens_in=10,
        tokens_out=5,
        latency_ms=100,
    )
```

### 3. Run the evaluation

```bash
agenteval run --suite suite.yaml --agent my_agent:run -v
```

## YAML Suite Format

```yaml
name: suite-name          # Required
agent: module:callable     # Default agent (can override via --agent)

defaults:                  # Optional defaults for all cases
  grader: contains
  grader_config: {}

cases:                     # Required, non-empty list
  - name: case-name        # Required
    input: "prompt text"   # Required
    expected:              # Grader-specific expected values
      output: "expected output"
      tools: ["tool_name"]
      pattern: "regex"
    grader: contains       # One of: exact, contains, regex, tool-check, llm-judge, custom
    grader_config: {}      # Grader-specific configuration
    tags: [smoke, fast]    # Optional tags for filtering
```

## Grader Types

| Grader | Description | Expected Fields |
|--------|-------------|-----------------|
| `exact` | Exact string match | `output` |
| `contains` | Substring match (case-insensitive) | `output` |
| `regex` | Regular expression match | `pattern` |
| `tool-check` | Verify specific tools were called | `tools` (list) |
| `llm-judge` | LLM-based evaluation | `criteria` (string) |
| `custom` | Custom Python grader function | `grader_config.callable` |

## CLI Usage

### Run evaluations

```bash
# Basic run
agenteval run --suite suite.yaml

# With agent override and verbose output
agenteval run --suite suite.yaml --agent my_agent:run -v

# Filter by tags
agenteval run --suite suite.yaml --tag smoke --tag fast

# Custom timeout and database
agenteval run --suite suite.yaml --timeout 60 --db results.db
```

### List past runs

```bash
agenteval list
agenteval list --suite-filter my-agent-tests --limit 10
```

### Compare runs (regression detection)

```bash
# Compare two runs
agenteval compare RUN_A RUN_B

# Multi-run comparison with statistical significance
agenteval compare RUN_A1,RUN_A2 vs RUN_B1,RUN_B2

# Adjust significance level
agenteval compare RUN_A RUN_B --alpha 0.01 --threshold 0.1
```

Comparison uses Welch's t-test to detect statistically significant regressions.

### Import from AgentLens

Import real agent sessions from an [AgentLens](https://github.com/your-org/agentlens) SQLite database as test cases:

```bash
# Import all sessions
agenteval import --from agentlens --db sessions.db -o suite.yaml

# Limit and customize
agenteval import --from agentlens --db sessions.db -o suite.yaml --limit 50 --grader contains --name my-suite
```

This maps AgentLens session events (LLM calls, tool calls, errors) to EvalCase format, auto-selecting `tool-check` grader when tools are detected.

## Comparison Workflow

1. **Baseline:** Run your agent against a suite and note the run ID
2. **Change:** Modify your agent
3. **Re-run:** Run the same suite again
4. **Compare:** `agenteval compare <baseline-id> <new-id>`
5. **Review:** Check for regressions (statistically significant score drops)

## Results Storage

All results are stored in SQLite (default: `agenteval.db`). Each run tracks:
- Per-case pass/fail, scores, and details
- Agent output and tools called
- Token usage and cost
- Latency

## Optional Dependencies

- **scipy** — Required for statistical comparison (Welch's t-test). Install: `pip install scipy`

## License

MIT
