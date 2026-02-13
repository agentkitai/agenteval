# AgentEval v0.2.0 — Architecture Document

**Author:** Winston (Architect) | **Date:** 2026-02-13

---

## Current Architecture (v0.1.0)

```
src/agenteval/
├── __init__.py          (3 lines)
├── cli.py               (310 lines)   — Click-based CLI
├── compare.py           (318 lines)   — Statistical comparison
├── loader.py            (85 lines)    — YAML suite loading
├── models.py            (73 lines)    — Dataclasses
├── runner.py            (119 lines)   — Async sequential runner
├── store.py             (159 lines)   — SQLite result storage
├── graders/
│   ├── __init__.py      (44 lines)    — Registry + base class
│   ├── exact.py, contains.py, regex.py, tool_check.py, custom.py, llm_judge.py
└── importers/
    ├── __init__.py      (1 line)
    └── agentlens.py     (272 lines)   — Basic importer
```

Total: ~1652 lines. Key insight: `AgentResult` already carries `latency_ms`, `cost_usd`, `tokens_in/out` — the latency and cost graders are trivial.

---

## Feature 1: CI Integration

### New Files
- `src/agenteval/ci.py` (~150 lines) — CI logic: threshold checking, regression detection, output formatting
- `src/agenteval/formatters/` — New package
  - `__init__.py` (~10 lines)
  - `json_fmt.py` (~40 lines) — JSON output
  - `junit.py` (~60 lines) — JUnit XML output

### Design

```python
# ci.py
@dataclass
class CIConfig:
    min_pass_rate: float = 1.0
    max_regression_pct: float = 0.0
    baseline_run_id: Optional[str] = None
    output_format: str = "text"  # text | json | junit

@dataclass
class CIResult:
    passed: bool
    run: EvalRun
    regressions: List[str]  # case names that regressed
    threshold_violations: List[str]  # human-readable reasons

def check_thresholds(run: EvalRun, config: CIConfig, store: Optional[ResultStore]) -> CIResult:
    ...
```

CLI integration: add `ci` command to `cli.py` (~40 lines). It calls `run_suite()` then `check_thresholds()`.

### Estimated Size: ~300 lines (ci.py + formatters + CLI additions)

---

## Feature 2: Advanced Graders

### New Files
- `src/agenteval/graders/json_schema_grader.py` (~45 lines)
- `src/agenteval/graders/semantic.py` (~60 lines)
- `src/agenteval/graders/latency.py` (~25 lines)
- `src/agenteval/graders/cost.py` (~25 lines)

### Design

All graders follow the existing `BaseGrader` pattern:

```python
class BaseGrader:
    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult: ...
```

**json_schema:**
```python
import json
import jsonschema

class JsonSchemaGrader(BaseGrader):
    def __init__(self, config: dict):
        self.schema = config.get("schema") or json.load(open(config["schema_file"]))

    async def grade(self, case, result):
        try:
            data = json.loads(result.output)
            jsonschema.validate(data, self.schema)
            return GradeResult(passed=True, score=1.0, reason="Valid JSON schema")
        except (json.JSONDecodeError, jsonschema.ValidationError) as e:
            return GradeResult(passed=False, score=0.0, reason=str(e))
```

**semantic:**
```python
class SemanticGrader(BaseGrader):
    def __init__(self, config: dict):
        self.threshold = config.get("threshold", 0.8)
        self.model_name = config.get("model", "all-MiniLM-L6-v2")
        self._model = None  # lazy load

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise ImportError("pip install sentence-transformers for semantic grading")
            self._model = SentenceTransformer(self.model_name)
        return self._model
```

**latency / cost:** Trivial — read from `AgentResult`, compare to threshold.

### Registry Update
Update `graders/__init__.py` to register all 4 new graders.

### Estimated Size: ~180 lines

---

## Feature 3: AgentLens Import Polish

### Modified Files
- `src/agenteval/importers/agentlens.py` — Refactor + extend (272 → ~450 lines)
- `src/agenteval/cli.py` — Add `import` command group (~50 lines)

### Design

```python
# agentlens.py additions

class AssertionGenerator:
    """Generates eval assertions from AgentLens session data."""

    def from_tool_calls(self, tool_calls: List[dict]) -> List[dict]:
        """tool call → tool_check assertion"""
        ...

    def from_output(self, output: str) -> List[dict]:
        """output → contains assertion with key phrases"""
        ...

class InteractiveReviewer:
    """Terminal-based case review/edit."""

    def review_case(self, case: dict) -> Optional[dict]:
        """Show case, prompt y/n/edit. Returns None if rejected."""
        ...

class BatchImporter:
    """Import multiple sessions matching a filter."""

    def fetch_sessions(self, server: str, filter_query: str) -> List[str]:
        ...

    def import_all(self, sessions: List[str], ...) -> EvalSuite:
        ...
```

### Estimated Size: ~250 lines (net new, including CLI)

---

## Feature 4: Parallel Execution

### Modified Files
- `src/agenteval/runner.py` — Add parallel support (119 → ~200 lines)
- `src/agenteval/progress.py` — New file (~60 lines)

### Design

```python
# runner.py changes

async def run_suite(
    suite: EvalSuite,
    agent_fn: AgentCallable,
    *,
    store: Optional[ResultStore] = None,
    timeout: float = 30.0,
    run_id: Optional[str] = None,
    parallel: int = 1,          # NEW
    on_result: Optional[Callable] = None,  # NEW — streaming callback
) -> EvalRun:
    if parallel <= 1:
        # existing sequential path (unchanged)
        ...
    else:
        semaphore = asyncio.Semaphore(parallel)
        async def _run_with_sem(case):
            async with semaphore:
                result = await _run_case(case, agent_fn, timeout)
                if on_result:
                    on_result(result)
                return result
        results = await asyncio.gather(*[_run_with_sem(c) for c in suite.cases])
```

```python
# progress.py
class ProgressBar:
    """Rich progress bar with simple fallback."""

    def __init__(self, total: int):
        try:
            from rich.progress import Progress
            self._rich = Progress(...)
        except ImportError:
            self._rich = None
        self.total = total
        self.completed = 0

    def update(self, result: EvalResult):
        self.completed += 1
        if self._rich:
            self._rich.update(...)
        else:
            print(f"  [{self.completed}/{self.total}] {result.case_name}: {'✓' if result.passed else '✗'}")
```

### Estimated Size: ~150 lines

---

## Feature 5: GitHub Actions Integration

### New Files
- `src/agenteval/github.py` (~120 lines) — GitHub API client + comment formatting
- `examples/agenteval.yml` (~40 lines) — Reusable workflow template

### Design

```python
# github.py
import os
import json
import urllib.request

class GitHubClient:
    def __init__(self):
        self.token = os.environ["GITHUB_TOKEN"]
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if event_path:
            with open(event_path) as f:
                self.event = json.load(f)
        self.repo = os.environ.get("GITHUB_REPOSITORY", "")

    def post_pr_comment(self, run: EvalRun, ci_result: CIResult):
        """Post or update a PR comment with eval results."""
        body = self._format_comment(run, ci_result)
        # Find existing comment by marker
        # POST/PATCH via urllib.request (no requests dependency)
        ...

    def _format_comment(self, run, ci_result) -> str:
        """Markdown table + summary."""
        ...

def generate_badge(pass_rate: float, output_path: str):
    """Generate SVG badge from template."""
    color = "#4c1" if pass_rate >= 0.9 else "#dfb317" if pass_rate >= 0.7 else "#e05d44"
    # Simple SVG template string
    ...
```

**Key decision:** Use `urllib.request` instead of `requests` to avoid a new dependency. GitHub REST API is simple enough.

### Estimated Size: ~200 lines (including badge SVG template)

---

## Dependency Changes

| Package | Type | Used By |
|---------|------|---------|
| `jsonschema` | Required | json_schema grader |
| `sentence-transformers` | Optional | semantic grader |
| `rich` | Optional | Progress bar |

**pyproject.toml extras:**
```toml
[project.optional-dependencies]
semantic = ["sentence-transformers>=2.0"]
rich = ["rich>=13.0"]
all = ["sentence-transformers>=2.0", "rich>=13.0"]
```

---

## Data Model Changes

No changes to existing dataclasses. `CIConfig` and `CIResult` are new additions in `ci.py`.

---

## Integration Points

```
CLI (cli.py)
  ├── agenteval run [--parallel N]  →  runner.run_suite()  →  progress.ProgressBar
  ├── agenteval ci                  →  runner.run_suite()  →  ci.check_thresholds()  →  formatters.*
  ├── agenteval import agentlens    →  importers.agentlens.*
  ├── agenteval github-comment      →  github.GitHubClient
  └── agenteval badge               →  github.generate_badge()
```

---

## Test Strategy

| Feature | Test Approach | Est. Tests |
|---------|--------------|------------|
| CI Integration | Unit: threshold logic, regression detection. Integration: full CI run with mock agent. Format validation (JSON schema, JUnit XSD). | ~25 |
| Advanced Graders | Unit: each grader with valid/invalid inputs. Edge cases: malformed JSON, missing deps. | ~30 |
| AgentLens Import | Unit: assertion generation. Integration: mock AgentLens API. Interactive mode: mock stdin. | ~20 |
| Parallel Execution | Unit: semaphore behavior. Integration: verify ordering, timeout enforcement, concurrency count. | ~15 |
| GitHub Actions | Unit: comment formatting, badge generation. Integration: mock GitHub API. | ~15 |
| **Total** | | **~105 new tests** |

Combined with existing 127 tests → **~232 tests** for v0.2.0.

---

## Line Count Estimate

| Component | New Lines |
|-----------|-----------|
| ci.py + formatters | ~300 |
| 4 graders | ~180 |
| AgentLens polish | ~250 |
| Parallel + progress | ~150 |
| GitHub integration | ~200 |
| CLI additions | ~100 |
| **Total new source** | **~1180** |
| **v0.2.0 total** | **~2830** |

Within the ~3000 target. 👍
