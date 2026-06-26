"""CLI command submodules for AgentEval.

Each submodule exposes a ``register(cli, helpers)`` function that adds
its Click commands to the CLI group.
"""

from agenteval.commands import (
    baseline,
    ci,
    compare,
    coverage,
    dashboard,
    doctor,
    evidence,
    examples,
    generate,
    importers,
    init,
    lint,
    list_cmd,
    profile,
    report,
    run,
    trends,
    verify,
    worker,
)

ALL_MODULES = [
    run,
    compare,
    list_cmd,
    profile,
    importers,
    ci,
    baseline,
    worker,
    generate,
    coverage,
    doctor,
    evidence,
    init,
    lint,
    report,
    examples,
    dashboard,
    trends,
    verify,
]


def register_all(cli, helpers: dict) -> None:
    """Register every command submodule on *cli*."""
    for mod in ALL_MODULES:
        mod.register(cli, helpers)
