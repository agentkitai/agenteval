FROM python:3.12-slim

WORKDIR /work

# Install agenteval with distributed extras for optional Redis support
RUN pip install --no-cache-dir agentevalkit[distributed]

# Copy example suite (override at runtime with -v)
COPY suite.yaml .

CMD ["agenteval", "run", "--suite", "suite.yaml"]
