"""Deterministic search over indexed file metadata and text."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3


@dataclass(frozen=True)
class SearchResult:
    """A search hit that deliberately contains metadata, not file contents."""

    kind: str
    id: str
    project_id: str
    path: str
    name: str
    language: str | None
    score: float


class SearchService:
    """Search files without an LLM or vector database."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def search(
        self,
        project_id: str,
        query: str,
        mode: str = "text",
        limit: int = 10,
        language: str | None = None,
    ) -> list[SearchResult]:
        """Search by ``name``, ``path``, ``text`` or ``metadata``."""

        if not query.strip():
            return []
        if limit < 1 or limit > 100:
            raise ValueError("limit 必须在 1 到 100 之间")
        if mode not in {"name", "path", "text", "metadata"}:
            raise ValueError(f"不支持的搜索模式: {mode}")

        params: list[object] = [project_id]
        where = ["f.project_id = ?", "f.status = 'active'"]
        if language:
            where.append("f.language = ?")
            params.append(language)
        pattern = f"%{query.strip()}%"
        if mode == "name":
            where.append("f.file_name LIKE ? COLLATE NOCASE")
            params.append(pattern)
            order = "f.file_name COLLATE NOCASE, f.current_path"
        elif mode == "path":
            where.append("f.current_path LIKE ? COLLATE NOCASE")
            params.append(pattern)
            order = "f.current_path COLLATE NOCASE"
        elif mode == "metadata":
            where.append(
                "(f.file_type LIKE ? OR f.language LIKE ? OR f.status LIKE ?) COLLATE NOCASE"
            )
            params.extend([pattern, pattern, pattern])
            order = "f.current_path COLLATE NOCASE"
        else:
            return self._text_search(project_id, query, limit, language)

        rows = self.connection.execute(
            "SELECT f.file_id, f.project_id, f.current_path, f.file_name, f.language "
            "FROM files f WHERE " + " AND ".join(where) + f" ORDER BY {order} LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [
            SearchResult("file", row["file_id"], row["project_id"], row["current_path"],
                         row["file_name"], row["language"], 1.0)
            for row in rows
        ]

    def _text_search(
        self, project_id: str, query: str, limit: int, language: str | None
    ) -> list[SearchResult]:
        """Use SQLite FTS5; only file identities are returned to callers."""

        fts_query = self._fts_query(query)
        if not fts_query:
            return []
        rows = self.connection.execute(
            "SELECT f.file_id, f.project_id, f.current_path, f.file_name, f.language, "
            "bm25(file_text_fts) AS rank FROM file_text_fts "
            "JOIN files f ON f.file_id = file_text_fts.file_id "
            "WHERE file_text_fts.project_id = ? AND f.status = 'active' "
            "AND file_text_fts MATCH ? AND (? IS NULL OR f.language = ?) "
            "ORDER BY rank LIMIT ?",
            (project_id, fts_query, language, language, limit),
        ).fetchall()
        return [
            SearchResult("file", row["file_id"], row["project_id"], row["current_path"],
                         row["file_name"], row["language"], float(-row["rank"]))
            for row in rows
        ]

    @staticmethod
    def _fts_query(query: str) -> str:
        """Convert free-form task text to safe AND terms for SQLite FTS5."""

        terms = re.findall(r"[\w\u3400-\u9fff]+", query, flags=re.UNICODE)
        return " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)

