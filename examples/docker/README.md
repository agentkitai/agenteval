# Running AgentEval in Docker

This example shows how to run agenteval in a Docker container, with an
optional Redis service for distributed mode.

## Quick start

```bash
# Build the image
docker build -t agenteval .

# Run a suite
docker run --rm -v $(pwd)/suite.yaml:/work/suite.yaml agenteval \
  agenteval run --suite suite.yaml --agent my_agent:run
```

## With Docker Compose (distributed mode)

```bash
docker compose up
```

This starts a Redis instance and runs the agenteval worker. You can then
submit jobs from the agenteval container.

## Customisation

- Mount your agent code into `/work` to make it importable.
- Set `OPENAI_API_KEY` via environment variable or `.env` file.
- Add extra pip packages in the Dockerfile as needed.
