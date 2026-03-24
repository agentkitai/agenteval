"""Adapter protocol and registry for AgentEval."""

from __future__ import annotations

import importlib
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

from agenteval.models import AgentResult


class BaseAdapter(ABC):
    """Abstract base class that all adapters must implement."""

    @abstractmethod
    def invoke(self, input: str) -> AgentResult: ...


_ADAPTER_REGISTRY: Dict[str, type] = {}


def _ensure_registry() -> None:
    if _ADAPTER_REGISTRY:
        return
    from agenteval.adapters.autogen import AutoGenAdapter
    from agenteval.adapters.crewai import CrewAIAdapter
    from agenteval.adapters.langchain import LangChainAdapter

    _ADAPTER_REGISTRY.update({
        "langchain": LangChainAdapter,
        "crewai": CrewAIAdapter,
        "autogen": AutoGenAdapter,
    })


def get_adapter(name: str, **kwargs: Any) -> BaseAdapter:
    """Get an adapter instance by name."""
    _ensure_registry()
    if name not in _ADAPTER_REGISTRY:
        raise ValueError(
            f"Unknown adapter: {name!r}. Available: {sorted(_ADAPTER_REGISTRY)}"
        )
    return _ADAPTER_REGISTRY[name](**kwargs)


_BLOCKED_MODULES = ("os", "sys", "subprocess", "shutil", "builtins")
_log = logging.getLogger(__name__)


def _import_agent(agent_ref: str) -> Any:
    """Import an object from a 'module:attr' string."""
    import os
    import sys

    if ":" not in agent_ref:
        raise ValueError(
            f"agent_ref must use 'module:attr' format, got {agent_ref!r}"
        )

    module_path, attr_name = agent_ref.rsplit(":", 1)

    # Block dangerous top-level modules
    top_level = module_path.split(".")[0]
    if top_level in _BLOCKED_MODULES:
        raise ValueError(
            f"Importing from {top_level!r} is blocked for security reasons"
        )

    # Block dunder attribute access
    if attr_name.startswith("__"):
        raise ValueError(
            f"Dunder attribute access ({attr_name!r}) is blocked for security reasons"
        )

    # Ensure CWD is importable (matches CLI behavior)
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
        _log.warning("Added %s to sys.path for agent import", cwd)

    mod = importlib.import_module(module_path)
    return getattr(mod, attr_name)
