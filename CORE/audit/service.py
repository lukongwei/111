"""Append-only audit writers shared by the local services."""

from __future__ import annotations

import json
import sqlite3
from typing import Iterable


class AuditService:
    """Write audit facts without update/delete methods."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def operation(self, agent: str, project_id: str | None, action: str,
                  target: str | None, reason: str, result: str, detail: str = "") -> None:
        self.connection.execute(
            "INSERT INTO operation_log(timestamp, agent, project_id, action, target, reason, result, detail) "
            "VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?)",
            (agent, project_id, action, target, reason, result, detail),
        )
        self.connection.commit()

    def decision(self, project_id: str | None, decision: str, reason: str,
                 alternatives: Iterable[str], uncertainty: str) -> int:
        cursor = self.connection.execute(
            "INSERT INTO decision_log(timestamp, project_id, decision, reason, alternatives, uncertainty) "
            "VALUES (datetime('now'), ?, ?, ?, ?, ?)",
            (project_id, decision, reason, json.dumps(list(alternatives), ensure_ascii=False), uncertainty),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def change(self, project_id: str | None, task: str | None, file_path: str,
               before_hash: str | None, after_hash: str | None, test_result: str,
               decision_id: int | None = None) -> None:
        self.connection.execute(
            "INSERT INTO change_log(timestamp, project_id, task, file_path, before_hash, after_hash, "
            "test_result, decision_id) VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?)",
            (project_id, task, file_path, before_hash, after_hash, test_result, decision_id),
        )
        self.connection.commit()

    def token(self, agent: str, project_id: str | None, task: str | None, purpose: str,
              input_tokens: int, output_tokens: int, cache_tokens: int,
              context_sources: list[str], result: str) -> None:
        if purpose not in {
            "context_reading", "code_generation", "code_analysis", "testing",
            "debugging", "documentation", "other",
        }:
            raise ValueError(f"不支持的 token audit purpose: {purpose}")
        total = input_tokens + output_tokens + cache_tokens
        self.connection.execute(
            "INSERT INTO token_audit(timestamp, agent, project_id, task, purpose, input_tokens, "
            "output_tokens, cache_tokens, total_tokens, context_sources, result) "
            "VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (agent, project_id, task, purpose, input_tokens, output_tokens, cache_tokens,
             total, json.dumps(context_sources, ensure_ascii=False), result),
        )
        self.connection.commit()

