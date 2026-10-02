"""Deterministic import, containment, test and basic call relations."""

from __future__ import annotations

import ast
from pathlib import Path
import sqlite3


class RelationIndexer:
    """Build relations from Python AST and indexed project paths."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def index_project(self, project_id: str, root: Path) -> dict[str, int]:
        files = self.connection.execute(
            "SELECT file_id, current_path, file_name FROM files "
            "WHERE project_id = ? AND status = 'active' ORDER BY current_path",
            (project_id,),
        ).fetchall()
        self.connection.execute("DELETE FROM relations WHERE project_id = ?", (project_id,))
        by_module: dict[str, str] = {}
        by_stem: dict[str, list[str]] = {}
        for file in files:
            path = Path(file["current_path"])
            module = ".".join(path.with_suffix("").parts)
            by_module[module] = file["file_id"]
            by_stem.setdefault(path.stem, []).append(file["file_id"])
        relation_count = 0
        for file in files:
            path = root / Path(file["current_path"])
            if path.suffix != ".py":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError):
                continue
            target_ids: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    target = by_module.get(name) or by_module.get(name.split(".")[0])
                    if target and target != file["file_id"]:
                        relation_count += self._insert(project_id, "file", file["file_id"], "imports", "file", target)
                        target_ids.add(target)
            if file["file_name"].startswith("test_") or file["file_name"].endswith("_test.py"):
                for target in target_ids:
                    relation_count += self._insert(project_id, "file", file["file_id"], "tests", "file", target)

            source_symbols = self.connection.execute(
                "SELECT symbol_id, name FROM symbols WHERE file_id = ?", (file["file_id"],)
            ).fetchall()
            symbols_by_name = {row["name"]: row["symbol_id"] for row in self.connection.execute(
                "SELECT symbol_id, name FROM symbols WHERE project_id = ?", (project_id,)
            ).fetchall()}
            for symbol in source_symbols:
                symbol_row = self.connection.execute(
                    "SELECT start_line, end_line FROM symbols WHERE symbol_id = ?",
                    (symbol["symbol_id"],),
                ).fetchone()
                relation_count += self._index_calls(
                    project_id, file, symbol, tree, symbols_by_name, symbol_row
                )
            for symbol in source_symbols:
                relation_count += self._insert(project_id, "file", file["file_id"], "contains", "symbol", symbol["symbol_id"])
        return {"relations": relation_count}

    def _index_calls(self, project_id, file, symbol, tree, symbols_by_name, symbol_row) -> int:
        count = 0
        for node in ast.walk(tree):
            if symbol_row and not (
                symbol_row["start_line"] <= getattr(node, "lineno", 0) <= symbol_row["end_line"]
            ):
                continue
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
                target = symbols_by_name.get(name)
                if target:
                    count += self._insert(project_id, "symbol", symbol["symbol_id"], "calls", "symbol", target)
        return count

    def _insert(self, project_id, source_type, source_id, relation_type, target_type, target_id) -> int:
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO relations(project_id, source_type, source_id, relation_type, "
            "target_type, target_id) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, source_type, source_id, relation_type, target_type, target_id),
        )
        return cursor.rowcount

