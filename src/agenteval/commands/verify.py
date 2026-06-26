"""The 'verify-evidence' command — independently verify eval evidence (#10)."""

from __future__ import annotations

import json

import click


def register(cli: click.Group, helpers: dict) -> None:
    """Register the verify-evidence command on the CLI group."""

    @cli.command(name="verify-evidence")
    @click.option("--run-id", default=None, help="Eval run id (resolves to session eval-<run-id>).")
    @click.option("--session-id", default=None, help="Explicit AgentLens session id (overrides --run-id).")
    @click.option("--agentlens-server", envvar="AGENTLENS_SERVER", default="", help="AgentLens base URL.")
    @click.option("--agentlens-api-key", envvar="AGENTLENS_API_KEY", default="", help="AgentLens API key (audit/admin role).")
    @click.option("--format", "fmt", default="text", type=click.Choice(["text", "json"]), show_default=True)
    def verify_evidence(run_id, session_id, agentlens_server, agentlens_api_key, fmt):
        """Independently verify a run's eval evidence in AgentLens.

        Re-walks the session's hash chain server-side and confirms it is intact and
        non-empty. Because ``eval_result`` can't be client-inserted, a verified
        eval session proves the evidence is server-authored — you can verify it,
        but you can't forge it. Exits non-zero if verification fails.

          agenteval verify-evidence --run-id RUN_ID \\
            --agentlens-server https://lens --agentlens-api-key $KEY
        """
        import agenteval.cli as _cli_mod
        _fail = _cli_mod._fail

        from agenteval.verify import (
            VerifyError,
            session_id_for_run,
            verify_eval_evidence,
        )

        sid = session_id or (session_id_for_run(run_id) if run_id else None)
        if not sid:
            _fail("Provide --run-id or --session-id.")
        if not agentlens_server:
            _fail("Provide --agentlens-server (or set AGENTLENS_SERVER).")
        if not agentlens_api_key:
            _fail("Provide --agentlens-api-key (or set AGENTLENS_API_KEY).")

        assert sid is not None  # _fail() raises; narrows the Optional for type-checkers
        try:
            result = verify_eval_evidence(server=agentlens_server, api_key=agentlens_api_key, session_id=sid)
        except VerifyError as e:
            _fail(str(e))

        if fmt == "json":
            click.echo(json.dumps(result, indent=2))
        else:
            mark = "OK" if result["verified"] else "FAIL"
            click.echo(
                f"[{mark}] session {sid}: verified={result['verified']} "
                f"(chain={result['chainVerified']}, sessions={result['sessionsVerified']})"
            )
            if result["brokenChains"]:
                click.echo(f"  broken chains: {result['brokenChains']}")

        if not result["verified"]:
            raise SystemExit(1)
