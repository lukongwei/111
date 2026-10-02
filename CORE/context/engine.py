"""Deterministic progressive Context Engine."""

from __future__ import annotations

from dataclasses import dataclass

from CORE.gateway.service import ContextGateway
from CORE.protocol.models import GatewayRequest


@dataclass(frozen=True)
class ContextItem:
    kind: str
    id: str
    path: str | None
    score: float
    reason: str
    content: str | None = None


@dataclass(frozen=True)
class ContextPackage:
    task: str
    project_id: str
    items: list[ContextItem]
    total_tokens: int


class ContextEngine:
    """Select and assemble a narrow context through the Gateway only."""

    def __init__(self, gateway: ContextGateway) -> None:
        self.gateway = gateway

    def assemble(
        self, project_id: str, task: str, agent: str = "context-engine", max_items: int = 8
    ) -> ContextPackage:
        """Search, expand direct relations and read candidates until the budget is full."""

        if not task.strip():
            raise ValueError("task 不能为空")
        search = self.gateway.handle(GatewayRequest(
            op="search", project_id=project_id, agent=agent, task=task,
            query=task, mode="text", limit=max_items,
        ))
        if not search.ok:
            raise RuntimeError(search.error)
        candidates = list(search.data or [])
        candidates.sort(key=lambda item: (-float(item.get("score", 0)), item.get("path", "")))
        expanded: list[tuple[dict[str, object], str]] = [
            (candidate, "text search") for candidate in candidates
        ]
        for candidate in candidates[:max_items]:
            relations = self.gateway.handle(GatewayRequest(
                op="relate", project_id=project_id, agent=agent, task=task,
                id=str(candidate["id"]), relation=["imports", "tests", "called_by", "tested_by"],
            ))
            if not relations.ok:
                continue
            for relation in relations.data or []:
                related_id = relation["target_id"] if relation["source_id"] == candidate["id"] else relation["source_id"]
                if relation["target_type"] == "file" or relation["source_type"] == "file":
                    expanded.append((
                        {"id": related_id, "score": float(candidate.get("score", 0)) * 0.8},
                        f"relation:{relation['relation_type']}",
                    ))
        items: list[ContextItem] = []
        seen: set[str] = set()
        for candidate, reason in expanded:
            if len(items) >= max_items:
                break
            file_id = str(candidate["id"])
            if file_id in seen:
                continue
            seen.add(file_id)
            response = self.gateway.handle(GatewayRequest(
                op="read", project_id=project_id, agent=agent, task=task, id=file_id
            ))
            if response.ok:
                read = response.data
                items.append(ContextItem(
                    kind=read["kind"], id=read["id"], path=read["path"],
                    score=float(candidate.get("score", 0)), reason=reason, content=read["content"],
                ))
        return ContextPackage(task, project_id, items, sum(
            int(self._estimate_tokens(item.content or "")) for item in items
        ))

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, (len(text) + 3) // 4) if text else 0

