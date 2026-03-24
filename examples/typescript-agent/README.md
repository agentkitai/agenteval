# Testing a TypeScript Agent with AgentEval

This example shows how to test a TypeScript/Node.js agent using agenteval
with a thin Python wrapper.

## Prerequisites

- Python 3.9+ with `agentevalkit` installed
- Node.js 18+ with npm

## Setup

```bash
cd examples/typescript-agent
npm install
```

## How it works

1. `agent.ts` — A simple TypeScript agent that echoes or transforms input.
2. `wrapper.py` — A Python wrapper that calls the TS agent via subprocess
   and returns an `AgentResult`.
3. `suite.yaml` — An agenteval test suite that uses the wrapper.

## Running

```bash
agenteval run --suite suite.yaml
```

The wrapper invokes `npx tsx agent.ts` as a subprocess, passes the input
via stdin, and captures stdout as the agent output.
