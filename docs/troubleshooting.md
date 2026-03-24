# Troubleshooting

Common issues and solutions for AgentEval.

---

## Agent Import Errors

### `ValueError: agent_ref must use 'module:attr' format`

The `--agent` flag expects `module:function` format:

```bash
# Wrong
agenteval run --suite suite.yaml --agent my_agent

# Correct
agenteval run --suite suite.yaml --agent my_module:run_agent
```

### `ModuleNotFoundError: No module named 'my_module'`

Ensure the module is importable from your current directory:

```bash
# Your agent file must be in the current directory or on PYTHONPATH
ls my_module.py  # Should exist

# Or install your package
pip install -e .
```

### `AttributeError: module 'my_module' has no attribute 'run_agent'`

Check that the function name after `:` matches an exported function in the module.

---

## Missing Dependencies

### `ImportError: Redis is required for distributed execution`

Install the distributed extra:

```bash
pip install agentevalkit[distributed]
```

### `ImportError: scipy is required for statistical comparison`

Install the stats extra for Welch's t-test:

```bash
pip install agentevalkit[stats]
# or: pip install scipy
```

AgentEval falls back to a pure-Python implementation if scipy is unavailable.

### `ImportError` for adapter frameworks

Install the appropriate extra:

```bash
pip install agentevalkit[langchain]   # LangChain adapter
pip install agentevalkit[crewai]      # CrewAI adapter
pip install agentevalkit[autogen]     # AutoGen adapter
```

---

## LLM Judge Grader

### `Error: OPENAI_API_KEY not set`

The `llm-judge` grader requires an OpenAI API key (or compatible API):

```bash
export OPENAI_API_KEY=sk-...
```

You can also configure a custom API base in the grader config:

```yaml
grader: llm-judge
grader_config:
  model: gpt-4o-mini
  api_base: https://your-api.com/v1
```

---

## Compare Command

### `Error: Could not parse compare arguments`

The compare command accepts two formats:

```bash
# Two single runs
agenteval compare RUN_ID_A RUN_ID_B

# Two groups (comma-separated, with 'vs')
agenteval compare RUN_A1,RUN_A2 vs RUN_B1,RUN_B2
```

Run IDs are the short hex IDs shown by `agenteval list`.

### `Error: Run not found`

Check available runs with:

```bash
agenteval list --limit 20
```

---

## YAML Suite Errors

### `Error: Suite file not found`

Ensure the path is correct:

```bash
agenteval run --suite ./suites/my_suite.yaml
```

### `Error: Invalid suite format`

Check your YAML syntax. Common issues:
- Missing `name` field
- Missing `cases` list
- Incorrect indentation
- Using tabs instead of spaces

Minimal valid suite:

```yaml
name: my-tests
agent: my_module:my_fn
cases:
  - name: test-1
    input: "Hello"
    expected:
      output_contains: ["hello"]
    grader: contains
```

---

## Database Issues

### `sqlite3.OperationalError: unable to open database file`

Check that the directory exists and is writable:

```bash
# Default location
ls -la agenteval.db

# Custom location
agenteval run --suite suite.yaml --db /path/to/results.db
```

### Corrupted database

Delete and re-run evaluations:

```bash
rm agenteval.db
agenteval run --suite suite.yaml
```

---

## Redis / Distributed Execution

### Workers not detected

Ensure workers are running and connected to the same Redis instance:

```bash
# Check Redis connectivity
redis-cli -u redis://localhost:6379 ping
# Should return: PONG

# Start a worker
agenteval worker --broker redis://localhost:6379 --agent my_module:my_fn
```

### Redis authentication errors

Use an authenticated URL:

```bash
agenteval run --suite suite.yaml --workers redis://:password@host:6379
```

### Security best practices

For production, use TLS-encrypted connections:

```bash
# Use rediss:// scheme for TLS
agenteval worker --broker rediss://:password@host:6380

# With custom CA certificate
export REDIS_CA_CERT=/path/to/ca.pem
```

---

## CI Integration

### Exit codes

- `0` — All cases passed
- `1` — One or more cases failed (or regressions detected with `--fail-on-regression`)

### GitHub PR comments not posting

Check your token permissions:

```bash
export GITHUB_TOKEN=ghp_...  # Needs 'pull_requests: write' permission
agenteval github-comment --run-id RUN_ID --repo owner/repo --pr 123
```

See [docs/github-actions.md](github-actions.md) for full CI setup.
