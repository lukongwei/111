"""Gateway 使用的结构化请求和响应模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_OPERATIONS = frozenset({"search", "describe", "read", "relate", "history", "status"})


@dataclass(frozen=True)
class ContextBudget:
    max_total_tokens: int = 8000
    max_files: int = 8
    max_read_operations: int = 8
    max_single_file_tokens: int = 4000
    max_request_count: int = 20


@dataclass(frozen=True)
class GatewayRequest:
    op: str
    project_id: str
    agent: str = "default"
    task: str | None = None
    query: str | None = None
    scope: str = "current_project"
    id: str | None = None
    relation: list[str] = field(default_factory=list)
    mode: str = "text"
    limit: int = 10
    language: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GatewayRequest":
        allowed = {
            "op", "project_id", "agent", "task", "query", "scope", "id",
            "relation", "mode", "limit", "language",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Request 包含未知字段: {sorted(unknown)}")
        if not isinstance(payload.get("op"), str) or payload["op"] not in SUPPORTED_OPERATIONS:
            raise ValueError(f"不支持的 op: {payload.get('op')}")
        if not isinstance(payload.get("project_id"), str) or not payload["project_id"]:
            raise ValueError("project_id 必须存在")
        relation = payload.get("relation", [])
        if not isinstance(relation, list) or not all(isinstance(item, str) for item in relation):
            raise ValueError("relation 必须是字符串数组")
        limit = payload.get("limit", 10)
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit 必须是整数")
        return cls(**payload)


@dataclass(frozen=True)
class GatewayResponse:
    ok: bool
    op: str
    data: Any = None
    error: str | None = None
    usage: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"ok": self.ok, "op": self.op}
        if self.ok:
            result["data"] = self.data
            result["usage"] = self.usage
        else:
            result["error"] = self.error
        return result

