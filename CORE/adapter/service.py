"""Model-neutral Agent Adapter protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from CORE.context.engine import ContextEngine, ContextPackage


@dataclass(frozen=True)
class AgentRequest:
    agent: str
    project_id: str
    task: str


class AgentAdapter:
    """Adapt any model callback to the same context-in/context-out contract."""

    def __init__(self, context_engine: ContextEngine) -> None:
        self.context_engine = context_engine

    def prepare(self, request: AgentRequest) -> ContextPackage:
        return self.context_engine.assemble(request.project_id, request.task, request.agent)

    def run(self, request: AgentRequest, model: Callable[[dict[str, Any]], Any]) -> Any:
        package = self.prepare(request)
        payload = {
            "task": package.task,
            "project_id": package.project_id,
            "context": [item.__dict__ for item in package.items],
            "usage": {"total_tokens": package.total_tokens},
        }
        return model(payload)

