"""Adapter protocol and registry for AgentEval."""

from __future__ import annotations

import importlib
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
    from agenteval.adapters.langchain import LangChainAdapter

    _ADAPTER_REGISTRY.update({
        "langchain": LangChainAdapter,
    })


def get_adapter(name: str, **kwargs: Any) -> BaseAdapter:
    """Get an adapter instance by name."""
    _ensure_registry()
    if name not in _ADAPTER_REGISTRY:
        raise ValueError(
            f"Unknown adapter: {name!r}. Available: {sorted(_ADAPTER_REGISTRY)}"
        )
    return _ADAPTER_REGISTRY[name](**kwargs)


def _import_agent(agent_ref: str) -> Any:
    """Import an object from a 'module:attr' string."""
    if ":" not in agent_ref:
        raise ValueError(
            f"agent_ref must use 'module:attr' format, got {agent_ref!r}"
        )
    module_path, attr_name = agent_ref.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, attr_name)
