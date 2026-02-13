"""Distributed execution for AgentEval."""


def __getattr__(name: str):
    if name == "Coordinator":
        from agenteval.distributed.coordinator import Coordinator
        return Coordinator
    if name == "Worker":
        from agenteval.distributed.worker import Worker
        return Worker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Coordinator", "Worker"]
