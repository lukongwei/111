"""Filesystem Index 的 SQLite 存储层。

数据库层只负责持久化和事务，不负责遍历文件系统或推断移动关系。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS counters (
    name TEXT PRIMARY KEY,
    next_value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    current_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    parent_path TEXT NOT NULL,
    file_type TEXT,
    language TEXT,
    size INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    modified_time_ns INTEGER NOT NULL,
    change_time_ns INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'deleted')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_project_status
    ON files(project_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_files_active_path
    ON files(project_id, current_path) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS file_paths (
    file_id TEXT NOT NULL REFERENCES files(file_id),
    relative_path TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    is_current INTEGER NOT NULL CHECK (is_current IN (0, 1)),
    PRIMARY KEY (file_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_file_paths_project_path
    ON file_paths(relative_path);

CREATE TABLE IF NOT EXISTS directories (
    directory_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    relative_path TEXT NOT NULL,
    parent_path TEXT NOT NULL,
    name TEXT NOT NULL,
    depth INTEGER NOT NULL,
    UNIQUE (project_id, relative_path)
);

CREATE TABLE IF NOT EXISTS index_runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    scanned_count INTEGER NOT NULL DEFAULT 0,
    added_count INTEGER NOT NULL DEFAULT 0,
    changed_count INTEGER NOT NULL DEFAULT 0,
    moved_count INTEGER NOT NULL DEFAULT 0,
    deleted_count INTEGER NOT NULL DEFAULT 0,
    hash_recomputed_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS scan_warnings (
    warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES index_runs(run_id),
    warning_type TEXT NOT NULL,
    relative_path TEXT,
    detail TEXT NOT NULL
);
"""

SCHEMA_VERSION = "1"


class IndexDatabase:
    """SQLite 连接和最小事务 API。"""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(SCHEMA)
        existing_version = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        if existing_version is not None and existing_version["value"] != SCHEMA_VERSION:
            self.connection.close()
            raise RuntimeError(
                f"不支持的 Index schema 版本: {existing_version['value']}，"
                f"当前版本为 {SCHEMA_VERSION}"
            )
        self.connection.execute(
            "INSERT OR IGNORE INTO metadata(key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        self.connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """提供显式事务；异常时回滚，避免留下半次扫描。"""

        self.connection.execute("BEGIN")
        try:
            yield self.connection
        except Exception:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "IndexDatabase":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

