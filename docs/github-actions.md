# GitHub Actions Integration

AgentEval integrates with GitHub Actions to post evaluation results as PR comments and generate badges.

## Setup

1. **Add a workflow** — copy `examples/agenteval.yml` to `.github/workflows/`
2. **Configure secrets** — `GITHUB_TOKEN` is provided automatically by Actions
3. **Create your suite** — define `suite.yaml` with your eval cases

## Commands

### `agenteval github-comment`

Posts (or updates) a PR comment with a results table.

```bash
agenteval github-comment --run <run_id> [--dry-run] [--db agenteval.db]
```

- `--dry-run` prints the markdown without posting
- Requires `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, and `GITHUB_EVENT_PATH` env vars (set automatically in Actions)
- Uses a hidden HTML marker to update existing comments instead of creating duplicates

### `agenteval badge`

Generates a shields.io-style SVG badge with the pass rate.

```bash
agenteval badge --run <run_id> --output badge.svg [--db agenteval.db]
```

Colors: green (≥90%), yellow (≥70%), red (<70%).

## Comment Format

The PR comment includes:
- Pass/fail status with emoji
- Summary line with pass rate and regression count
- Results table (case name, status, score, latency, cost)
- Regression callout section if any detected
