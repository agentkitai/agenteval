"""The 'worker' command."""

from __future__ import annotations

import sys

import click


def register(cli: click.Group, helpers: dict) -> None:
    """Register the worker command on the CLI group."""

    @cli.group("worker", invoke_without_command=True)
    @click.option("--broker", default=None, help="Redis broker URL.")
    @click.option("--concurrency", default=1, show_default=True, type=int, help="Max concurrent tasks.")
    @click.pass_context
    def worker_cmd(ctx: click.Context, broker: str | None, concurrency: int) -> None:
        """Start a distributed worker that processes eval tasks.

        Examples:

          agenteval worker --broker redis://localhost:6379

          agenteval worker --broker redis://localhost:6379 --concurrency 4
        """
        ctx.ensure_object(dict)
        ctx.obj["broker"] = broker
        ctx.obj["concurrency"] = concurrency

        if ctx.invoked_subcommand is not None:
            return

        # Default behaviour: start worker
        if broker is None:
            click.echo("Error: --broker is required.", err=True)
            sys.exit(1)

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

    @worker_cmd.command("diagnostics")
    @click.option("--broker", required=True, help="Redis broker URL.")
    def diagnostics_cmd(broker: str) -> None:
        """Show distributed system diagnostics.

        Displays active worker count, queue depths, dead-letter counts,
        and task status summaries.
        """
        from agenteval.distributed.coordinator import _get_redis

        redis_mod = _get_redis()
        r = redis_mod.Redis.from_url(broker, decode_responses=True)

        # Active workers
        workers = list(r.scan_iter("agenteval:worker:*", count=100))
        click.echo(f"Active workers: {len(workers)}")

        # Task queues
        task_keys = list(r.scan_iter("agenteval:tasks:*", count=100))
        if task_keys:
            click.echo("\nTask queues:")
            for key in sorted(task_keys):
                depth = r.llen(key)
                run_id = key.split(":", 2)[-1]
                click.echo(f"  {run_id}: {depth} pending")
        else:
            click.echo("\nTask queues: (none)")

        # Dead-letter queues
        dl_keys = list(r.scan_iter("agenteval:dead-letter:*", count=100))
        if dl_keys:
            click.echo("\nDead-letter queues:")
            for key in sorted(dl_keys):
                count = r.llen(key)
                run_id = key.split(":", 2)[-1]
                click.echo(f"  {run_id}: {count} tasks")
        else:
            click.echo("\nDead-letter queues: (none)")

        # Task status summaries
        status_keys = list(r.scan_iter("agenteval:task-status:*", count=100))
        if status_keys:
            click.echo("\nTask status:")
            for key in sorted(status_keys):
                statuses = r.hgetall(key)
                run_id = key.split(":", 2)[-1]
                pending = sum(1 for v in statuses.values() if v == "pending")
                completed = sum(1 for v in statuses.values() if v == "completed")
                failed = sum(1 for v in statuses.values() if v == "failed")
                click.echo(
                    f"  {run_id}: {completed} completed, {pending} pending, {failed} failed"
                )
        else:
            click.echo("\nTask status: (none)")
