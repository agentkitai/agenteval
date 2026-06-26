"""The 'calibrate' command — LLM-judge calibration certificate (#12)."""

from __future__ import annotations

import json

import click


def register(cli: click.Group, helpers: dict) -> None:
    """Register the calibrate command on the CLI group."""

    @cli.command()
    @click.argument("run_id")
    @click.option("--labels", "labels_file", required=True, type=click.Path(exists=True),
                  help='JSON mapping of reference labels: {"case_name": true|false}.')
    @click.option("--judge-model", default="unknown", help="The judge model under calibration.")
    @click.option("--suite-file", default=None, type=click.Path(exists=True),
                  help="Suite file → provenance hash (#11) scoping the cert to an exact dataset version.")
    @click.option("--db", default="agenteval.db", show_default=True, help="SQLite database path.")
    @click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), show_default=True)
    def calibrate(run_id, labels_file, judge_model, suite_file, db, fmt):
        """Build an LLM-judge calibration certificate for a run.

        Compares the run's per-case verdicts against reference (human) labels and
        records agreement + Cohen's kappa, scoped to the dataset (suite hash) and
        the reference distribution. Notarized via content hash (+ optional HMAC).

          agenteval calibrate RUN_ID --labels labels.json --judge-model claude-...
        """
        import agenteval.cli as _cli_mod
        _fail = _cli_mod._fail

        from agenteval.calibration import build_calibration_certificate
        from agenteval.store import ResultStore

        with open(labels_file, encoding="utf-8") as f:
            labels = json.load(f)
        if not isinstance(labels, dict):
            _fail("--labels must be a JSON object {case_name: bool}.")

        store = ResultStore(db)
        try:
            run = store.get_run(run_id)
            if run is None:
                _fail(f"Run '{run_id}' not found.")
        finally:
            store.close()

        assert run is not None  # _fail() raises otherwise
        predicted, reference = [], []
        for r in run.results:
            if r.case_name in labels:
                predicted.append(bool(r.passed))
                reference.append(bool(labels[r.case_name]))
        if not predicted:
            _fail("No run cases matched the provided labels.")

        suite_hash = None
        if suite_file:
            from agenteval.loader import load_suite
            from agenteval.provenance import suite_content_hash
            suite_hash = suite_content_hash(load_suite(suite_file))

        cert = build_calibration_certificate(
            judge_model=judge_model, dataset=run.suite,
            predicted=predicted, reference=reference, suite_hash=suite_hash,
        )

        if fmt == "json":
            click.echo(json.dumps(cert, indent=2))
        else:
            m = cert["metrics"]
            click.echo(
                f"judge={cert['judgeModel']} dataset={cert['dataset']} n={m['n']} "
                f"agreement={m['agreement']} kappa={m['cohenKappa']} hash={cert['contentHash'][:16]}…"
            )
