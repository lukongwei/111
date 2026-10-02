"""Central dashboard read model; it never becomes an independent project store."""

from __future__ import annotations

import sqlite3


class DashboardService:
    """Expose dense L0/L1/L2 metrics from the shared Index database."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def overview(self) -> dict[str, object]:
        scalar = lambda query: self.connection.execute(query).fetchone()[0]
        return {
            "projects": scalar("SELECT COUNT(*) FROM projects"),
            "active_files": scalar("SELECT COUNT(*) FROM files WHERE status = 'active'"),
            "deleted_files": scalar("SELECT COUNT(*) FROM files WHERE status = 'deleted'"),
            "symbols": scalar("SELECT COUNT(*) FROM symbols"),
            "relations": scalar("SELECT COUNT(*) FROM relations"),
            "operations": scalar("SELECT COUNT(*) FROM operation_log"),
            "token_total": scalar("SELECT COALESCE(SUM(total_tokens), 0) FROM token_audit"),
        }

    def projects(self) -> list[dict[str, object]]:
        rows = self.connection.execute(
            "SELECT p.project_id, p.name, p.root_path, "
            "(SELECT COUNT(*) FROM files f WHERE f.project_id = p.project_id AND f.status = 'active') AS active_files "
            "FROM projects p ORDER BY p.project_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def alerts(self) -> list[dict[str, object]]:
        rows = self.connection.execute(
            "SELECT 'failed_index_run' AS alert_type, project_id AS target, error_message AS detail "
            "FROM index_runs WHERE status = 'failed' "
            "UNION ALL SELECT 'gateway_rejection', project_id, detail FROM operation_log WHERE result = 'rejected' "
            "ORDER BY alert_type"
        ).fetchall()
        return [dict(row) for row in rows]

