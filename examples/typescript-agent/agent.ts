/**
 * Simple TypeScript agent for agenteval testing.
 *
 * Reads a JSON payload from stdin: { "input": "..." }
 * Writes a JSON response to stdout: { "output": "..." }
 *
 * Supported commands (prefix-based):
 *   "echo ..."      — echoes back the rest of the input
 *   "upper ..."     — converts the rest to uppercase
 *   "reverse ..."   — reverses the rest of the string
 *   anything else   — returns the input unchanged
 */

async function main() {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf-8").trim();

  let input: string;
  try {
    const payload = JSON.parse(raw);
    input = payload.input ?? raw;
  } catch {
    input = raw;
  }

  let output: string;
  if (input.startsWith("echo ")) {
    output = input.slice(5);
  } else if (input.startsWith("upper ")) {
    output = input.slice(6).toUpperCase();
  } else if (input.startsWith("reverse ")) {
    output = input.slice(8).split("").reverse().join("");
  } else {
    output = input;
  }

  const result = JSON.stringify({ output });
  process.stdout.write(result + "\n");
}

main().catch((err) => {
  process.stderr.write(String(err) + "\n");
  process.exit(1);
});
