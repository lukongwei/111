"""Filesystem Index 的项目注册和增量扫描服务。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid

from .database import IndexDatabase
from .exclusions import should_ignore_directory, should_ignore_file
from .metadata import calculate_sha256, detect_language
from .models import FileRecord, ProjectRecord, ScanResult
from .relations import RelationIndexer
from .search import SearchResult, SearchService
from .symbols import PythonSymbolIndexer


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _allocate_id(connection: sqlite3.Connection, counter: str, prefix: str) -> str:
    row = connection.execute(
        "SELECT next_value FROM counters WHERE name = ?", (counter,)
    ).fetchone()
    value = row["next_value"] if row else 1
    connection.execute(
        "INSERT INTO counters(name, next_value) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET next_value = excluded.next_value",
        (counter, value + 1),
    )
    return f"{prefix}-{value:06d}"


class IndexService:
    """通过稳定 API 管理项目和 Filesystem Index。

    输入是显式注册的项目根目录。扫描只读取该根目录内的常规文件，
    输出为结构化记录和扫描统计；写入副作用由 SQLite 事务管理。
    """

    def __init__(self, database: IndexDatabase) -> None:
        self.database = database
        self.search_service = SearchService(database.connection)

    def register_project(self, name: str, root_path: Path | str) -> ProjectRecord:
        """注册项目；路径必须已存在且为目录，重复注册返回原记录。"""

        root = Path(root_path).resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError(root)
        if not name.strip():
            raise ValueError("项目名称不能为空")

        timestamp = _now()
        connection = self.database.connection
        with self.database.transaction():
            row = connection.execute(
                "SELECT * FROM projects WHERE root_path = ?", (str(root),)
            ).fetchone()
            if row is None:
                project_id = _allocate_id(connection, "project", "P")
                connection.execute(
                    "INSERT INTO projects(project_id, name, root_path, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (project_id, name.strip(), str(root), timestamp, timestamp),
                )
                row = connection.execute(
                    "SELECT * FROM projects WHERE project_id = ?", (project_id,)
                ).fetchone()
        return self._project_from_row(row)

    def get_project(self, project_id: str) -> ProjectRecord:
        row = self.database.connection.execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"未知项目 ID: {project_id}")
        return self._project_from_row(row)

    def scan_project(self, project_id: str) -> ScanResult:
        """扫描注册项目并原子写入差异。

        文件发现和 Hash 读取在 DB 写事务前完成；DB 应用阶段失败会整体回滚。
        每次运行记录单独提交，因此失败原因仍可审计。
        """

        project = self.get_project(project_id)
        run_id = str(uuid.uuid4())
        started_at = _now()
        connection = self.database.connection
        connection.execute(
            "INSERT INTO index_runs(run_id, project_id, started_at, status) "
            "VALUES (?, ?, ?, 'running')",
            (run_id, project_id, started_at),
        )
        connection.commit()

        counts = {
            "scanned_count": 0,
            "added_count": 0,
            "changed_count": 0,
            "moved_count": 0,
            "deleted_count": 0,
            "hash_recomputed_count": 0,
            "warning_count": 0,
        }
        text_refresh_ids: set[str] = set()
        try:
            snapshot, directories, warnings = self._discover(project.root_path)
            counts["scanned_count"] = len(snapshot)
            counts["warning_count"] = len(warnings)
            with self.database.transaction():
                self._apply_snapshot(
                    project, run_id, snapshot, directories, warnings, counts, text_refresh_ids
                )
                self._refresh_text_index(project, snapshot, text_refresh_ids)
                connection.execute(
                    "UPDATE index_runs SET completed_at = ?, status = 'completed', "
                    "scanned_count = ?, added_count = ?, changed_count = ?, moved_count = ?, "
                    "deleted_count = ?, hash_recomputed_count = ? WHERE run_id = ?",
                    (
                        _now(), counts["scanned_count"], counts["added_count"],
                        counts["changed_count"], counts["moved_count"],
                        counts["deleted_count"], counts["hash_recomputed_count"], run_id,
                    ),
                )
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            connection.execute(
                "UPDATE index_runs SET completed_at = ?, status = 'failed', error_message = ?, "
                "scanned_count = ?, added_count = ?, changed_count = ?, moved_count = ?, "
                "deleted_count = ?, hash_recomputed_count = ? "
                "WHERE run_id = ?",
                (
                    _now(), message, counts["scanned_count"], counts["added_count"],
                    counts["changed_count"], counts["moved_count"], counts["deleted_count"],
                    counts["hash_recomputed_count"], run_id,
                ),
            )
            connection.commit()
            return ScanResult(
                run_id=run_id,
                project_id=project_id,
                status="failed",
                error_message=message,
                **counts,
            )

        return ScanResult(
            run_id=run_id, project_id=project_id, status="completed", **counts
        )

    def list_files(self, project_id: str, include_deleted: bool = False) -> list[FileRecord]:
        """列出项目文件；默认只返回 active 文件。"""

        self.get_project(project_id)
        query = "SELECT * FROM files WHERE project_id = ?"
        if not include_deleted:
            query += " AND status = 'active'"
        query += " ORDER BY current_path"
        rows = self.database.connection.execute(query, (project_id,)).fetchall()
        return [self._file_from_row(row) for row in rows]

    def get_file(self, file_id: str) -> FileRecord:
        row = self.database.connection.execute(
            "SELECT * FROM files WHERE file_id = ?", (file_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"未知文件 ID: {file_id}")
        return self._file_from_row(row)

    def list_directories(self, project_id: str) -> list[dict[str, object]]:
        self.get_project(project_id)
        rows = self.database.connection.execute(
            "SELECT directory_id, relative_path, parent_path, name, depth "
            "FROM directories WHERE project_id = ? ORDER BY depth, relative_path",
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_warnings(self, run_id: str) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT warning_type, relative_path, detail FROM scan_warnings "
            "WHERE run_id = ? ORDER BY warning_id",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_file_paths(self, file_id: str) -> list[dict[str, object]]:
        """返回文件的当前路径与历史路径。"""

        self.get_file(file_id)
        rows = self.database.connection.execute(
            "SELECT relative_path, first_seen_at, last_seen_at, is_current "
            "FROM file_paths WHERE file_id = ? ORDER BY first_seen_at, relative_path",
            (file_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def search(
        self, project_id: str, query: str, mode: str = "text", limit: int = 10,
        language: str | None = None,
    ) -> list[SearchResult]:
        """搜索文件身份和元数据，不直接返回文件全文。"""

        self.get_project(project_id)
        return self.search_service.search(project_id, query, mode, limit, language)

    def index_code(self, project_id: str) -> dict[str, int]:
        """为已索引项目建立 Python Symbol 与确定性 Relation。"""

        project = self.get_project(project_id)
        with self.database.transaction():
            symbols = PythonSymbolIndexer(self.database.connection).index_project(
                project_id, project.root_path
            )
            relations = RelationIndexer(self.database.connection).index_project(
                project_id, project.root_path
            )
        return {**symbols, **relations}

    def list_symbols(self, project_id: str, query: str | None = None) -> list[dict[str, object]]:
        self.get_project(project_id)
        sql = "SELECT * FROM symbols WHERE project_id = ?"
        params: list[object] = [project_id]
        if query:
            sql += " AND (name LIKE ? OR qualified_name LIKE ?)"
            params.extend([f"%{query}%", f"%{query}%"])
        sql += " ORDER BY qualified_name, start_line"
        return [dict(row) for row in self.database.connection.execute(sql, params).fetchall()]

    def get_symbol(self, symbol_id: str) -> dict[str, object]:
        row = self.database.connection.execute(
            "SELECT * FROM symbols WHERE symbol_id = ?", (symbol_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"未知 Symbol ID: {symbol_id}")
        return dict(row)

    def relate(self, project_id: str, object_id: str, relation_types: list[str] | None = None) -> list[dict[str, object]]:
        self.get_project(project_id)
        params: list[object] = [project_id, object_id, object_id]
        query = (
            "SELECT source_type, source_id, relation_type, target_type, target_id, confidence "
            "FROM relations WHERE project_id = ? AND (source_id = ? OR target_id = ?)"
        )
        if relation_types:
            placeholders = ",".join("?" for _ in relation_types)
            query += f" AND relation_type IN ({placeholders})"
            params.extend(relation_types)
        return [dict(row) for row in self.database.connection.execute(query, params).fetchall()]

    def history(self, project_id: str, file_id: str) -> list[dict[str, object]]:
        self.get_project(project_id)
        self.get_file(file_id)
        rows = self.database.connection.execute(
            "SELECT relative_path, first_seen_at, last_seen_at, is_current "
            "FROM file_paths WHERE file_id = ? ORDER BY first_seen_at", (file_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def status(self, project_id: str) -> dict[str, object]:
        project = self.get_project(project_id)
        latest = self.database.connection.execute(
            "SELECT * FROM index_runs WHERE project_id = ? ORDER BY started_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return {
            "project_id": project_id,
            "root_exists": project.root_path.is_dir(),
            "index_status": latest["status"] if latest else "never_scanned",
            "last_run_id": latest["run_id"] if latest else None,
            "active_files": self.database.connection.execute(
                "SELECT COUNT(*) FROM files WHERE project_id = ? AND status = 'active'",
                (project_id,),
            ).fetchone()[0],
            "deleted_files": self.database.connection.execute(
                "SELECT COUNT(*) FROM files WHERE project_id = ? AND status = 'deleted'",
                (project_id,),
            ).fetchone()[0],
        }

    def read_file_content(self, project_id: str, relative_path: str) -> str:
        """由受控 Index 层读取项目内相对路径。"""

        project = self.get_project(project_id)
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("非法项目相对路径")
        path = (project.root_path / relative).resolve()
        path.relative_to(project.root_path)
        return path.read_text(encoding="utf-8", errors="replace")

    def _discover(
        self, root: Path
    ) -> tuple[list[dict[str, object]], list[str], list[tuple[str, str, str]]]:
        snapshot: list[dict[str, object]] = []
        directories: list[str] = ["."]
        warnings: list[tuple[str, str, str]] = []
        database_path = self.database.path
        managed_database_files = {
            database_path,
            Path(f"{database_path}-wal"),
            Path(f"{database_path}-shm"),
            Path(f"{database_path}-journal"),
        }
        pending = [root]
        while pending:
            current = pending.pop()
            try:
                entries = sorted(current.iterdir(), key=lambda item: item.name.casefold())
            except OSError as error:
                relative = current.relative_to(root).as_posix() or "."
                raise OSError(f"无法完整扫描目录 {relative}: {error}") from error

            child_directories: list[Path] = []
            for path in entries:
                relative_path = path.relative_to(root).as_posix()
                try:
                    if path in managed_database_files:
                        continue
                    if path.is_symlink():
                        warnings.append(("symlink_skipped", relative_path, "符号链接不进入索引"))
                    elif path.is_dir():
                        if not should_ignore_directory(path):
                            directories.append(relative_path)
                            child_directories.append(path)
                    elif path.is_file() and not should_ignore_file(path):
                        stat = path.stat()
                        snapshot.append(
                            {
                                "path": relative_path,
                                "file_name": path.name,
                                "parent_path": Path(relative_path).parent.as_posix()
                                if Path(relative_path).parent.as_posix() != "."
                                else ".",
                                "file_type": path.suffix.lower() or None,
                                "language": detect_language(path),
                                "size": stat.st_size,
                                "modified_time_ns": stat.st_mtime_ns,
                                "change_time_ns": stat.st_ctime_ns,
                                "absolute_path": path,
                            }
                        )
                except OSError as error:
                    raise OSError(f"无法读取文件元数据 {relative_path}: {error}") from error
            pending.extend(reversed(child_directories))
        snapshot.sort(key=lambda item: str(item["path"]))
        directories.sort(key=lambda item: (item.count("/"), item))
        return snapshot, directories, warnings

    def _apply_snapshot(
        self,
        project: ProjectRecord,
        run_id: str,
        snapshot: list[dict[str, object]],
        directories: list[str],
        warnings: list[tuple[str, str, str]],
        counts: dict[str, int],
        text_refresh_ids: set[str],
    ) -> None:
        connection = self.database.connection
        project_id = project.project_id
        now = _now()
        old_rows = connection.execute(
            "SELECT * FROM files WHERE project_id = ? AND status = 'active'",
            (project_id,),
        ).fetchall()
        old_by_path = {row["current_path"]: row for row in old_rows}
        new_by_path = {str(item["path"]): item for item in snapshot}

        # Hash 只对新文件或元数据发生变化的文件计算；时间精度不足时不会漏判。
        new_hashes: dict[str, str] = {}
        for path, item in new_by_path.items():
            old = old_by_path.get(path)
            unchanged_metadata = (
                old is not None
                and old["size"] == item["size"]
                and old["modified_time_ns"] == item["modified_time_ns"]
                and old["change_time_ns"] == item["change_time_ns"]
            )
            if unchanged_metadata:
                item["content_hash"] = old["content_hash"]
            else:
                item["content_hash"] = calculate_sha256(item["absolute_path"])
                counts["hash_recomputed_count"] += 1
            new_hashes[path] = str(item["content_hash"])

        missing_paths = set(old_by_path) - set(new_by_path)
        new_paths = set(new_by_path) - set(old_by_path)
        old_by_hash: dict[str, list[str]] = {}
        new_by_hash: dict[str, list[str]] = {}
        for path in missing_paths:
            old_by_hash.setdefault(old_by_path[path]["content_hash"], []).append(path)
        for path in new_paths:
            new_by_hash.setdefault(new_hashes[path], []).append(path)

        moved: dict[str, str] = {}
        for digest in old_by_hash.keys() & new_by_hash.keys():
            old_candidates = old_by_hash[digest]
            new_candidates = new_by_hash[digest]
            if len(old_candidates) == len(new_candidates) == 1:
                moved[old_candidates[0]] = new_candidates[0]
                counts["moved_count"] += 1
            else:
                for path in new_candidates:
                    warnings.append(
                        (
                            "ambiguous_move",
                            path,
                            "多个消失/新增文件具有相同 Hash，无法确定移动对应关系",
                        )
                    )
        counts["warning_count"] = len(warnings)

        matched_old = set(moved)
        for path in missing_paths:
            old = old_by_path[path]
            connection.execute(
                "UPDATE files SET status = 'deleted', deleted_at = ?, last_seen_at = ? "
                "WHERE file_id = ?",
                (now, now, old["file_id"]),
            )
            connection.execute(
                "UPDATE file_paths SET is_current = 0, last_seen_at = ? "
                "WHERE file_id = ? AND is_current = 1",
                (now, old["file_id"]),
            )

        for path, item in new_by_path.items():
            old = old_by_path.get(path)
            if old is not None:
                file_id = old["file_id"]
                file_changed = any(
                    old[field] != item[value]
                    for field, value in (
                        ("file_name", "file_name"),
                        ("parent_path", "parent_path"),
                        ("file_type", "file_type"),
                        ("language", "language"),
                        ("size", "size"),
                        ("content_hash", "content_hash"),
                        ("modified_time_ns", "modified_time_ns"),
                        ("change_time_ns", "change_time_ns"),
                    )
                )
                if old["content_hash"] != item["content_hash"]:
                    counts["changed_count"] += 1
                if not file_changed:
                    continue
                text_refresh_ids.add(file_id)
                connection.execute(
                    "UPDATE files SET file_name = ?, parent_path = ?, file_type = ?, language = ?, "
                    "size = ?, content_hash = ?, modified_time_ns = ?, change_time_ns = ?, last_seen_at = ?, "
                    "deleted_at = NULL WHERE file_id = ?",
                    (
                        item["file_name"], item["parent_path"], item["file_type"],
                        item["language"], item["size"], item["content_hash"],
                        item["modified_time_ns"], item["change_time_ns"], now, file_id,
                    ),
                )
                continue

            old_path = next((old for old, new in moved.items() if new == path), None)
            if old_path is not None:
                old = old_by_path[old_path]
                file_id = old["file_id"]
                connection.execute(
                    "UPDATE files SET current_path = ?, file_name = ?, parent_path = ?, "
                    "file_type = ?, language = ?, size = ?, modified_time_ns = ?, change_time_ns = ?, "
                    "status = 'active', deleted_at = NULL, last_seen_at = ? WHERE file_id = ?",
                    (
                        path, item["file_name"], item["parent_path"], item["file_type"],
                        item["language"], item["size"], item["modified_time_ns"],
                        item["change_time_ns"], now, file_id,
                    ),
                )
                connection.execute(
                    "UPDATE file_paths SET is_current = 0 WHERE file_id = ?", (file_id,)
                )
                self._upsert_path(file_id, path, now)
                text_refresh_ids.add(file_id)
                continue

            # 同一路径文件被删除后重新出现时恢复原 ID；ID 永不复用。
            deleted = connection.execute(
                "SELECT * FROM files WHERE project_id = ? AND current_path = ? AND status = 'deleted'",
                (project_id, path),
            ).fetchone()
            if deleted is not None:
                file_id = deleted["file_id"]
                connection.execute(
                    "UPDATE files SET file_name = ?, parent_path = ?, file_type = ?, language = ?, "
                    "size = ?, content_hash = ?, modified_time_ns = ?, change_time_ns = ?, status = 'active', "
                    "last_seen_at = ?, deleted_at = NULL WHERE file_id = ?",
                    (
                        item["file_name"], item["parent_path"], item["file_type"],
                        item["language"], item["size"], item["content_hash"],
                        item["modified_time_ns"], item["change_time_ns"], now, file_id,
                    ),
                )
                self._upsert_path(file_id, path, now)
                counts["changed_count"] += 1
                text_refresh_ids.add(file_id)
            else:
                file_id = _allocate_id(connection, "file", "F")
                connection.execute(
                    "INSERT INTO files(file_id, project_id, current_path, file_name, parent_path, "
                    "file_type, language, size, content_hash, modified_time_ns, change_time_ns, status, "
                    "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
                    (
                        file_id, project_id, path, item["file_name"], item["parent_path"],
                        item["file_type"], item["language"], item["size"], item["content_hash"],
                        item["modified_time_ns"], item["change_time_ns"], now, now,
                    ),
                )
                counts["added_count"] += 1
                text_refresh_ids.add(file_id)
            self._upsert_path(file_id, path, now)

        deleted_or_moved = missing_paths
        for path in deleted_or_moved:
            old = old_by_path[path]
            file_id = old["file_id"]
            if path in matched_old:
                continue
            counts["deleted_count"] += 1

        self._replace_directories(project_id, directories)
        for warning_type, relative_path, detail in warnings:
            connection.execute(
                "INSERT INTO scan_warnings(run_id, warning_type, relative_path, detail) "
                "VALUES (?, ?, ?, ?)",
                (run_id, warning_type, relative_path, detail),
            )

        for file_id in (
            row["file_id"] for row in connection.execute(
                "SELECT file_id FROM files WHERE project_id = ? AND status = 'deleted'",
                (project_id,),
            ).fetchall()
        ):
            connection.execute("DELETE FROM file_text_fts WHERE file_id = ?", (file_id,))

    def _refresh_text_index(
        self, project: ProjectRecord, snapshot: list[dict[str, object]], refresh_ids: set[str]
    ) -> None:
        """只为新增或内容/路径变更的文件更新 FTS，避免重复扫描重读全部文件。"""

        by_id = {
            row["file_id"]: row for row in self.database.connection.execute(
                "SELECT file_id, current_path FROM files WHERE project_id = ? AND status = 'active'",
                (project.project_id,),
            ).fetchall()
        }
        snapshot_by_path = {str(item["path"]): item for item in snapshot}
        for file_id in refresh_ids:
            row = by_id.get(file_id)
            self.database.connection.execute("DELETE FROM file_text_fts WHERE file_id = ?", (file_id,))
            if row is None:
                continue
            item = snapshot_by_path.get(row["current_path"])
            if item is None:
                continue
            path = project.root_path / Path(row["current_path"])
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            self.database.connection.execute(
                "INSERT INTO file_text_fts(project_id, file_id, relative_path, content) VALUES (?, ?, ?, ?)",
                (project.project_id, file_id, row["current_path"], content),
            )

    def _replace_directories(self, project_id: str, paths: list[str]) -> None:
        connection = self.database.connection
        existing = {
            row["relative_path"]: row["directory_id"]
            for row in connection.execute(
                "SELECT directory_id, relative_path FROM directories WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        }
        connection.execute("DELETE FROM directories WHERE project_id = ?", (project_id,))
        for path in paths:
            parent = "" if path == "." else Path(path).parent.as_posix()
            if parent == ".":
                parent = ""
            directory_id = existing.get(path) or _allocate_id(connection, "directory", "D")
            name = Path(path).name if path != "." else "."
            connection.execute(
                "INSERT INTO directories(directory_id, project_id, relative_path, parent_path, name, depth) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (directory_id, project_id, path, parent, name, 0 if path == "." else path.count("/") + 1),
            )

    def _upsert_path(self, file_id: str, path: str, timestamp: str) -> None:
        self.database.connection.execute(
            "INSERT INTO file_paths(file_id, relative_path, first_seen_at, last_seen_at, is_current) "
            "VALUES (?, ?, ?, ?, 1) ON CONFLICT(file_id, relative_path) DO UPDATE SET "
            "last_seen_at = excluded.last_seen_at, is_current = 1",
            (file_id, path, timestamp, timestamp),
        )

    @staticmethod
    def _project_from_row(row: sqlite3.Row) -> ProjectRecord:
        return ProjectRecord(
            project_id=row["project_id"], name=row["name"], root_path=Path(row["root_path"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _file_from_row(row: sqlite3.Row) -> FileRecord:
        return FileRecord(**dict(row))

