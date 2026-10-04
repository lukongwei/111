"""Workspace Console application service.

This module adapts the existing Index, Gateway and Context Engine to a small
browser-facing API. It does not read project files directly for the UI: file
content and context are obtained through ContextGateway and ContextEngine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from CORE.context import ContextEngine
from CORE.gateway import ContextGateway
from CORE.index import IndexService
from CORE.protocol import GatewayRequest


class ConsoleService:
    """Expose the existing Workspace capabilities as UI-sized operations."""

    def __init__(self, index: IndexService) -> None:
        self.index = index
        self.gateway = ContextGateway(index)
        self.context = ContextEngine(self.gateway)

    def projects(self) -> list[dict[str, object]]:
        rows = self.index.database.connection.execute(
            "SELECT project_id, name, root_path, created_at, updated_at "
            "FROM projects ORDER BY project_id"
        ).fetchall()
        result = []
        for row in rows:
            project_id = row["project_id"]
            status = self.index.status(project_id)
            counts = self._counts(project_id)
            result.append({**dict(row), "status": status, "counts": counts})
        return result

    def register(self, name: str, root_path: str) -> dict[str, object]:
        project = self.index.register_project(name, Path(root_path))
        return {"project": project.__dict__, "status": self.index.status(project.project_id)}

    def scan(self, project_id: str) -> dict[str, object]:
        result = self.index.scan_project(project_id)
        return {"scan": result.__dict__, "status": self.index.status(project_id)}

    def code_index(self, project_id: str) -> dict[str, object]:
        result = self.index.index_code(project_id)
        return {"index": result, "status": self.index.status(project_id),
                "counts": self._counts(project_id)}

    def search(self, project_id: str, query: str, mode: str, limit: int) -> list[dict[str, object]]:
        response = self.gateway.handle(GatewayRequest(
            op="search", project_id=project_id, agent="workspace-console",
            query=query, mode=mode, limit=limit,
        ))
        return self._require(response)

    def object_detail(self, project_id: str, object_id: str) -> dict[str, object]:
        described = self._require(self.gateway.handle(GatewayRequest(
            op="describe", project_id=project_id, agent="workspace-console", id=object_id,
        )))
        relations = self._require(self.gateway.handle(GatewayRequest(
            op="relate", project_id=project_id, agent="workspace-console", id=object_id,
        )))
        detail: dict[str, object] = {"object": described, "relations": relations}
        if described.get("kind") == "file":
            file_id = str(described["file_id"])
            symbols = self.index.list_symbols(project_id)
            detail["symbols"] = [symbol for symbol in symbols if symbol["file_id"] == file_id]
        else:
            detail["symbols"] = [described]
        read = self._require(self.gateway.handle(GatewayRequest(
            op="read", project_id=project_id, agent="workspace-console", id=object_id,
        )))
        detail["content"] = read
        return detail

    def assemble_context(self, project_id: str, task: str, max_items: int) -> dict[str, object]:
        package = self.context.assemble(
            project_id, task, agent="workspace-console", max_items=max_items,
        )
        return {
            "task": package.task,
            "project_id": package.project_id,
            "items": [item.__dict__ for item in package.items],
            "total_tokens": package.total_tokens,
        }

    def _counts(self, project_id: str) -> dict[str, int]:
        connection = self.index.database.connection
        return {
            "files": connection.execute(
                "SELECT COUNT(*) FROM files WHERE project_id = ? AND status = 'active'",
                (project_id,),
            ).fetchone()[0],
            "symbols": connection.execute(
                "SELECT COUNT(*) FROM symbols WHERE project_id = ?", (project_id,)
            ).fetchone()[0],
            "relations": connection.execute(
                "SELECT COUNT(*) FROM relations WHERE project_id = ?", (project_id,)
            ).fetchone()[0],
        }

    @staticmethod
    def _require(response: Any) -> Any:
        if not response.ok:
            raise ValueError(response.error or "Gateway request failed")
        return response.data
