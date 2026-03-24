"""CLI command submodules for AgentEval.

Each submodule exposes a ``register(cli, helpers)`` function that adds
its Click commands to the CLI group.
"""

from agenteval.commands import (
    baseline,
    ci,
    compare,
    coverage,
    generate,
    importers,
    list_cmd,
    profile,
    run,
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
]


def register_all(cli, helpers: dict) -> None:
    """Register every command submodule on *cli*."""
    for mod in ALL_MODULES:
        mod.register(cli, helpers)
