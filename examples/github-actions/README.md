# GitHub Actions CI Templates for AgentEval

Reusable workflow templates for running agenteval in CI.

## Templates

### basic.yml

Minimal workflow: installs agenteval, runs a test suite, and fails on
non-zero exit code.

### with-comparison.yml

Runs a suite, compares results with a stored baseline, and posts a
summary comment on the pull request.

### with-gates.yml

Runs a suite with quality gates. Fails the build if any metric
regresses beyond the configured threshold.

## Usage

Copy the desired `.yml` file into your repository's `.github/workflows/`
directory and adjust the suite path, agent reference, and any thresholds
to match your project.
