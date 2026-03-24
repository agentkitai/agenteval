"""Python wrapper that calls the TypeScript agent via subprocess.

Usage in suite.yaml:
    agent: wrapper:run
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from agenteval.models import AgentResult

_AGENT_DIR = Path(__file__).parent


def run(input: str) -> AgentResult:
    """Invoke the TypeScript agent and return an AgentResult."""
    payload = json.dumps({"input": input})

    start = time.perf_counter()
    proc = subprocess.run(
        ["npx", "tsx", "agent.ts"],
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(_AGENT_DIR),
        timeout=30,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    if proc.returncode != 0:
        return AgentResult(
            output=f"ERROR: {proc.stderr.strip()}",
            latency_ms=elapsed_ms,
            metadata={"exit_code": proc.returncode},
        )

    try:
        data = json.loads(proc.stdout.strip())
        output = data.get("output", proc.stdout.strip())
    except json.JSONDecodeError:
        output = proc.stdout.strip()

    return AgentResult(
        output=output,
        latency_ms=elapsed_ms,
        metadata={"exit_code": proc.returncode},
    )
