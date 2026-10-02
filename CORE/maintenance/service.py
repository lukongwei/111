"""Deterministic maintenance checks; explanations can be added by a later Agent."""

from __future__ import annotations

from pathlib import Path
import sqlite3


class MaintenanceService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def check(self) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        projects = self.connection.execute("SELECT project_id, root_path FROM projects").fetchall()
        for project in projects:
            root = Path(project["root_path"])
            if not root.is_dir():
                issues.append({"type": "missing_project_root", "project_id": project["project_id"], "detail": str(root)})
            failed = self.connection.execute(
                "SELECT COUNT(*) FROM index_runs WHERE project_id = ? AND status = 'failed'",
                (project["project_id"],),
            ).fetchone()[0]
            if failed:
                issues.append({"type": "failed_index_runs", "project_id": project["project_id"], "detail": str(failed)})
        orphan_symbols = self.connection.execute(
            "SELECT COUNT(*) FROM symbols s LEFT JOIN files f ON f.file_id = s.file_id WHERE f.file_id IS NULL"
        ).fetchone()[0]
        if orphan_symbols:
            issues.append({"type": "orphan_symbols", "project_id": "", "detail": str(orphan_symbols)})
        return issues

