"""唯一的 Agent -> Index 访问边界。"""

from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import threading

from CORE.index.service import IndexService
from CORE.protocol.models import ContextBudget, GatewayRequest, GatewayResponse


SENSITIVE_MARKERS = frozenset({
    "env", "credential", "credentials", "password", "passwords", "secret",
    "secrets", "token", "tokens", "private", "apikey", "api_key",
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
        # 同一数据库连接使用固定受控预算；请求中的 agent 名称不是安全身份，
        # 也不接受调用方传入 session_id 伪造新额度。多会话隔离应由外部受信服务管理。
        self.session_id = "process-default"
        self._budget_lock = threading.RLock()
        self._register_budget()

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

    def _register_budget(self) -> None:
        values = (
            self.session_id, self.budget.max_total_tokens, self.budget.max_files,
            self.budget.max_read_operations, self.budget.max_single_file_tokens,
            self.budget.max_request_count,
        )
        row = self.connection.execute(
            "SELECT max_total_tokens, max_files, max_read_operations, max_single_file_tokens, "
            "max_request_count FROM gateway_sessions WHERE session_id = ?",
            (self.session_id,),
        ).fetchone()
        if row is not None and tuple(row) != values[1:]:
            raise ValueError("Gateway session 的 Context Budget 不可在运行中放宽或改变")
        self.connection.execute(
            "INSERT OR IGNORE INTO gateway_sessions(session_id, max_total_tokens, max_files, "
            "max_read_operations, max_single_file_tokens, max_request_count) VALUES (?, ?, ?, ?, ?, ?)",
            values,
        )
        self.connection.commit()

    def _dispatch(self, request: GatewayRequest) -> object:
        if request.scope != "current_project":
            raise GatewayError("当前只允许 scope=current_project")
        if request.op == "search":
            if not request.query:
                raise GatewayError("search 需要 query")
            return [result.__dict__ for result in self.index.search(
                request.project_id, request.query, request.mode, request.limit, request.language
            ) if not self._is_sensitive_path(result.path)]
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
            self._assert_object_scope(request.project_id, request.id, allow_deleted=False)
            return self.index.relate(request.project_id, request.id, request.relation)
        if request.op == "history":
            if not request.id:
                raise GatewayError("history 需要 id")
            file = self.index.get_file(request.id)
            if file.project_id != request.project_id:
                raise GatewayError("文件不属于当前项目")
            if file.status != "active":
                raise GatewayError("已删除或非活动文件历史禁止读取")
            history = self.index.history(request.project_id, request.id)
            if any(self._is_sensitive_path(item["relative_path"]) for item in history):
                raise GatewayError("敏感文件历史禁止读取")
            return history
        return self.index.status(request.project_id)

    def _describe(self, project_id: str, object_id: str) -> dict[str, object]:
        try:
            file = self.index.get_file(object_id)
            if file.project_id != project_id:
                raise GatewayError("对象不属于当前项目")
            if self._is_sensitive_path(file.current_path):
                raise GatewayError("敏感文件禁止描述")
            return {"kind": "file", **file.__dict__}
        except KeyError:
            symbol = self.index.get_symbol(object_id)
            if symbol["project_id"] != project_id:
                raise GatewayError("对象不属于当前项目")
            owner = self.index.get_file(symbol["file_id"])
            if owner.status != "active" or self._is_sensitive_path(owner.current_path):
                raise GatewayError("Symbol 所属文件禁止描述")
            return {"kind": "symbol", **symbol}

    def _read(self, request: GatewayRequest) -> dict[str, object]:
        try:
            symbol = self.index.get_symbol(request.id or "")
        except KeyError:
            symbol = None
        if symbol is not None:
            if symbol["project_id"] != request.project_id:
                raise GatewayError("Symbol 不属于当前项目")
            self._assert_file_id_allowed(symbol["file_id"])
            file = self.index.get_file(symbol["file_id"])
            self._reserve_read(request)
            content = self._read_path(request.project_id, file.current_path, file.file_id)
            lines = content.splitlines()
            selected = "\n".join(lines[max(0, symbol["start_line"] - 1):symbol["end_line"]])
            return self._bounded_read(request, file.file_id, symbol["symbol_id"], file.current_path, selected, "symbol")
        file = self.index.get_file(request.id or "")
        if file.project_id != request.project_id:
            raise GatewayError("文件不属于当前项目")
        self._assert_file_id_allowed(file.file_id)
        self._reserve_read(request)
        content = self._read_path(request.project_id, file.current_path, file.file_id)
        return self._bounded_read(request, file.file_id, file.file_id, file.current_path, content, "file")

    def _read_path(self, project_id: str, relative_path: str, file_id: str) -> str:
        if self._is_sensitive_path(relative_path):
            raise GatewayError("敏感文件禁止读取")
        try:
            return self.index.read_file_content(project_id, relative_path, file_id)
        except (ValueError, OSError) as error:
            raise GatewayError(str(error)) from error

    def _bounded_read(self, request, file_id, object_id, path, content, kind):
        tokens = max(1, (len(content) + 3) // 4)
        if tokens > self.budget.max_single_file_tokens:
            raise GatewayError("超过 max_single_file_tokens")
        with self._budget_lock:
            row = self._usage_row(request.project_id)
            if row["token_count"] + tokens > self.budget.max_total_tokens:
                raise GatewayError("超过 max_total_tokens")
            file_exists = self.connection.execute(
                "SELECT 1 FROM gateway_file_usage WHERE session_id = ? AND project_id = ? AND file_id = ?",
                (self.session_id, request.project_id, file_id),
            ).fetchone()
            file_count = self.connection.execute(
                "SELECT COUNT(*) FROM gateway_file_usage WHERE session_id = ? AND project_id = ?",
                (self.session_id, request.project_id),
            ).fetchone()[0]
            if not file_exists and file_count >= self.budget.max_files:
                raise GatewayError("超过 max_files")
            self.connection.execute(
                "UPDATE gateway_usage SET token_count = token_count + ? "
                "WHERE session_id = ? AND project_id = ?",
                (tokens, self.session_id, request.project_id),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO gateway_file_usage(session_id, project_id, file_id) VALUES (?, ?, ?)",
                (self.session_id, request.project_id, file_id),
            )
            self.connection.commit()
        return {"kind": kind, "id": object_id, "path": path, "content": content, "tokens": tokens}

    def _reserve_read(self, request: GatewayRequest) -> None:
        """Reserve a read slot before touching the project file."""

        with self._budget_lock:
            row = self._usage_row(request.project_id)
            if row["read_count"] >= self.budget.max_read_operations:
                raise GatewayError("超过 max_read_operations")
            self.connection.execute(
                "UPDATE gateway_usage SET read_count = read_count + 1 "
                "WHERE session_id = ? AND project_id = ?",
                (self.session_id, request.project_id),
            )
            self.connection.commit()

    def _assert_file_id_allowed(self, file_id: str) -> None:
        file = self.index.get_file(file_id)
        if file.status != "active":
            raise GatewayError("已删除或非活动文件禁止读取")
        if self._is_sensitive_path(file.current_path):
            raise GatewayError("敏感文件禁止读取")

    def _assert_object_scope(self, project_id: str, object_id: str, allow_deleted: bool) -> None:
        try:
            file = self.index.get_file(object_id)
        except KeyError:
            symbol = self.index.get_symbol(object_id)
            if symbol["project_id"] != project_id:
                raise GatewayError("对象不属于当前项目")
            owner = self.index.get_file(symbol["file_id"])
            if not allow_deleted and owner.status != "active":
                raise GatewayError("对象所属文件不是 active")
            if self._is_sensitive_path(owner.current_path):
                raise GatewayError("敏感对象禁止访问")
            return
        if file.project_id != project_id:
            raise GatewayError("对象不属于当前项目")
        if not allow_deleted and file.status != "active":
            raise GatewayError("对象不是 active")
        if self._is_sensitive_path(file.current_path):
            raise GatewayError("敏感对象禁止访问")

    @staticmethod
    def _is_sensitive_path(relative_path: str) -> bool:
        for part in Path(relative_path).parts:
            lowered = part.casefold()
            if lowered.startswith(".env"):
                return True
            stem = lowered.split(".", 1)[0]
            normalized = "".join(character for character in stem if character.isalnum() or character == "_")
            compact = normalized.replace("_", "")
            segments = {segment for segment in normalized.replace("_", " ").split()}
            if stem in SENSITIVE_MARKERS or segments & SENSITIVE_MARKERS:
                return True
            if any(marker in compact for marker in ("credential", "password", "secret", "token", "privatekey", "apikey")):
                return True
        return False

    def _check_budget(self, request: GatewayRequest) -> None:
        with self._budget_lock:
            self.connection.execute(
                "INSERT OR IGNORE INTO gateway_usage(session_id, project_id) VALUES (?, ?)",
                (self.session_id, request.project_id),
            )
            row = self._usage_row(request.project_id)
            if row["request_count"] >= self.budget.max_request_count:
                raise GatewayError("超过 max_request_count")
            self.connection.execute(
                "UPDATE gateway_usage SET request_count = request_count + 1 "
                "WHERE session_id = ? AND project_id = ?",
                (self.session_id, request.project_id),
            )
            self.connection.commit()

    def _usage_row(self, project_id: str) -> sqlite3.Row:
        self.connection.execute(
            "INSERT OR IGNORE INTO gateway_usage(session_id, project_id) VALUES (?, ?)",
            (self.session_id, project_id),
        )
        return self.connection.execute(
            "SELECT * FROM gateway_usage WHERE session_id = ? AND project_id = ?",
            (self.session_id, project_id),
        ).fetchone()

    def _usage(self, request: GatewayRequest) -> dict[str, int]:
        row = self._usage_row(request.project_id)
        return {
            "requests": row["request_count"],
            "reads": row["read_count"],
            "tokens": row["token_count"],
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

