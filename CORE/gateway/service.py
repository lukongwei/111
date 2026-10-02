"""唯一的 Agent -> Index 访问边界。"""

from __future__ import annotations

from pathlib import Path
import json
import sqlite3

from CORE.index.service import IndexService
from CORE.protocol.models import ContextBudget, GatewayRequest, GatewayResponse


SENSITIVE_PARTS = frozenset({
    ".env", "credentials", "credential", "password", "secret", "token",
    "private_key", "private-key", "apikey", "api_key",
})


class GatewayError(Exception):
    """A request was rejected before it could expose local information."""


class ContextGateway:
    """Validate, authorize, budget and audit structured context requests."""

    def __init__(
        self,
        index: IndexService,
        budget: ContextBudget | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self.index = index
        self.budget = budget or ContextBudget()
        self.connection = connection or index.database.connection
        self._request_counts: dict[str, int] = {}
        self._read_counts: dict[str, int] = {}
        self._file_counts: dict[str, set[str]] = {}
        self._token_counts: dict[str, int] = {}

    def handle(self, request: GatewayRequest | dict[str, object]) -> GatewayResponse:
        """Handle one request; all rejected requests are audited."""

        try:
            parsed = request if isinstance(request, GatewayRequest) else GatewayRequest.from_dict(request)
            self._check_budget(parsed)
            data = self._dispatch(parsed)
            self._audit(parsed, "gateway", "accepted", json.dumps({"op": parsed.op}, ensure_ascii=False))
            return GatewayResponse(True, parsed.op, data=data, usage=self._usage(parsed))
        except (GatewayError, KeyError, ValueError, OSError, sqlite3.Error) as error:
            op = request.op if isinstance(request, GatewayRequest) else str(request.get("op", "unknown"))
            agent = request.agent if isinstance(request, GatewayRequest) else str(request.get("agent", "unknown"))
            project_id = request.project_id if isinstance(request, GatewayRequest) else str(request.get("project_id", ""))
            self._audit_fields(agent, project_id, "gateway", "rejected", str(error))
            return GatewayResponse(False, op, error=str(error))

    def _dispatch(self, request: GatewayRequest) -> object:
        if request.scope != "current_project":
            raise GatewayError("当前只允许 scope=current_project")
        if request.op == "search":
            if not request.query:
                raise GatewayError("search 需要 query")
            return [result.__dict__ for result in self.index.search(
                request.project_id, request.query, request.mode, request.limit, request.language
            )]
        if request.op == "describe":
            if not request.id:
                raise GatewayError("describe 需要 id")
            return self._describe(request.project_id, request.id)
        if request.op == "read":
            if not request.id:
                raise GatewayError("read 需要 id")
            return self._read(request)
        if request.op == "relate":
            if not request.id:
                raise GatewayError("relate 需要 id")
            return self.index.relate(request.project_id, request.id, request.relation)
        if request.op == "history":
            if not request.id:
                raise GatewayError("history 需要 id")
            return self.index.history(request.project_id, request.id)
        return self.index.status(request.project_id)

    def _describe(self, project_id: str, object_id: str) -> dict[str, object]:
        try:
            file = self.index.get_file(object_id)
            if file.project_id != project_id:
                raise GatewayError("对象不属于当前项目")
            return {"kind": "file", **file.__dict__}
        except KeyError:
            symbol = self.index.get_symbol(object_id)
            if symbol["project_id"] != project_id:
                raise GatewayError("对象不属于当前项目")
            return {"kind": "symbol", **symbol}

    def _read(self, request: GatewayRequest) -> dict[str, object]:
        self._read_counts[request.agent] = self._read_counts.get(request.agent, 0) + 1
        if self._read_counts[request.agent] > self.budget.max_read_operations:
            raise GatewayError("超过 max_read_operations")
        try:
            symbol = self.index.get_symbol(request.id or "")
        except KeyError:
            symbol = None
        if symbol is not None:
            if symbol["project_id"] != request.project_id:
                raise GatewayError("Symbol 不属于当前项目")
            self._assert_file_id_allowed(symbol["file_id"])
            file = self.index.get_file(symbol["file_id"])
            content = self._read_path(request.project_id, file.current_path)
            lines = content.splitlines()
            selected = "\n".join(lines[max(0, symbol["start_line"] - 1):symbol["end_line"]])
            return self._bounded_read(request, symbol["symbol_id"], file.current_path, selected, "symbol")
        file = self.index.get_file(request.id or "")
        if file.project_id != request.project_id:
            raise GatewayError("文件不属于当前项目")
        self._assert_file_id_allowed(file.file_id)
        content = self._read_path(request.project_id, file.current_path)
        return self._bounded_read(request, file.file_id, file.current_path, content, "file")

    def _read_path(self, project_id: str, relative_path: str) -> str:
        if self._is_sensitive(Path(relative_path), Path(".")):
            raise GatewayError("敏感文件禁止读取")
        try:
            return self.index.read_file_content(project_id, relative_path)
        except (ValueError, OSError) as error:
            raise GatewayError(str(error)) from error

    def _bounded_read(self, request, object_id, path, content, kind):
        tokens = max(1, (len(content) + 3) // 4)
        if tokens > self.budget.max_single_file_tokens:
            raise GatewayError("超过 max_single_file_tokens")
        if self._token_counts.get(request.agent, 0) + tokens > self.budget.max_total_tokens:
            raise GatewayError("超过 max_total_tokens")
        files = self._file_counts.setdefault(request.agent, set())
        files.add(object_id)
        if len(files) > self.budget.max_files:
            raise GatewayError("超过 max_files")
        self._token_counts[request.agent] = self._token_counts.get(request.agent, 0) + tokens
        return {"kind": kind, "id": object_id, "path": path, "content": content, "tokens": tokens}

    def _assert_file_id_allowed(self, file_id: str) -> None:
        file = self.index.get_file(file_id)
        self._is_sensitive(Path(file.current_path), Path("."))
        if any(part.lower() in SENSITIVE_PARTS for part in Path(file.current_path).parts):
            raise GatewayError("敏感文件禁止读取")

    @staticmethod
    def _is_sensitive(path: Path, root: Path) -> bool:
        return any(part.lower() in SENSITIVE_PARTS or part.lower().startswith(".env") for part in path.parts)

    def _check_budget(self, request: GatewayRequest) -> None:
        count = self._request_counts.get(request.agent, 0) + 1
        if count > self.budget.max_request_count:
            raise GatewayError("超过 max_request_count")
        self._request_counts[request.agent] = count

    def _usage(self, request: GatewayRequest) -> dict[str, int]:
        return {
            "requests": self._request_counts.get(request.agent, 0),
            "reads": self._read_counts.get(request.agent, 0),
            "tokens": self._token_counts.get(request.agent, 0),
        }

    def _audit(self, request: GatewayRequest, action: str, result: str, detail: str) -> None:
        self._audit_fields(request.agent, request.project_id, action, result, detail)

    def _audit_fields(self, agent: str, project_id: str, action: str, result: str, detail: str) -> None:
        self.connection.execute(
            "INSERT INTO operation_log(timestamp, agent, project_id, action, target, reason, result, detail) "
            "VALUES (datetime('now'), ?, ?, ?, NULL, 'gateway request', ?, ?)",
            (agent, project_id or None, action, result, detail),
        )
        self.connection.commit()

