"""The 'worker' command."""

from __future__ import annotations

import sys

import click


def register(cli: click.Group, helpers: dict) -> None:
    """Register the worker command on the CLI group."""

    @cli.command("worker")
    @click.option("--broker", required=True, help="Redis broker URL.")
    @click.option("--concurrency", default=1, show_default=True, type=int, help="Max concurrent tasks.")
    def worker_cmd(broker: str, concurrency: int) -> None:
        """Start a distributed worker that processes eval tasks.

        Examples:

          agenteval worker --broker redis://localhost:6379

          agenteval worker --broker redis://localhost:6379 --concurrency 4
        """
        from agenteval.distributed.worker import Worker

        if concurrency < 1:
            click.echo("Error: --concurrency must be >= 1.", err=True)
            sys.exit(1)

        worker = Worker(broker, concurrency=concurrency)
        click.echo(f"Starting worker {worker.worker_id} (concurrency={concurrency})...")
        try:
            worker.start()
        except KeyboardInterrupt:
            pass
        finally:
            worker.stop()
            click.echo("Worker stopped.")
