"""CLI entry point for AgentEval.

This module is a thin bootstrap: it defines the Click group, shared
helpers, and delegates to ``agenteval.commands`` for every sub-command.
"""

from __future__ import annotations

import importlib
import os
import sys

import click

from agenteval import __version__

# ── Shared helpers used across command submodules ────────────────────────


def _fail(message: str) -> None:
    """Print an error message to stderr and exit with code 1."""
    click.echo(f"Error: {message}", err=True)
    sys.exit(1)


def _no_color() -> bool:
    """Return True if color output should be suppressed (https://no-color.org/)."""
    return "NO_COLOR" in os.environ


def _style(text: str, **kwargs) -> str:
    """Wrapper around click.style that respects the NO_COLOR convention."""
    if _no_color():
        return text
    return click.style(text, **kwargs)


def _resolve_callable(dotted_path: str):
    """Import and return a callable from a dotted path like 'pkg.mod:func'."""
    # Ensure CWD is in sys.path so local modules can be imported
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    if ":" not in dotted_path:
        raise click.BadParameter(
            f"Agent callable must use 'module:attribute' format, got '{dotted_path}'"
        )
    module_path, attr_name = dotted_path.rsplit(":", 1)
    try:
        mod = importlib.import_module(module_path)
    except ImportError as e:
        raise click.BadParameter(f"Cannot import module '{module_path}': {e}") from e
    try:
        fn = getattr(mod, attr_name)
    except AttributeError:
        raise click.BadParameter(
            f"Module '{module_path}' has no attribute '{attr_name}'"
        )
    if not callable(fn):
        raise click.BadParameter(f"'{dotted_path}' is not callable")
    return fn


# ── Click group ──────────────────────────────────────────────────────────


@click.group()
@click.version_option(version=__version__, prog_name="agenteval")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """AgentEval \u2014 Testing and evaluation framework for AI agents."""
    ctx.color = False if _no_color() else None


# ── Register all commands from submodules ────────────────────────────────

_helpers = {
    "_fail": _fail,
    "_no_color": _no_color,
    "_style": _style,
    "_resolve_callable": _resolve_callable,
}

from agenteval.commands import register_all  # noqa: E402

register_all(cli, _helpers)
