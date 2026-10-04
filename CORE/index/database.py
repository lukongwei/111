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

CREATE VIRTUAL TABLE IF NOT EXISTS file_text_fts USING fts5(
    project_id UNINDEXED,
    file_id UNINDEXED,
    relative_path,
    content,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS symbols (
    symbol_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL REFERENCES files(file_id),
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    parent_symbol_id TEXT REFERENCES symbols(symbol_id),
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    language TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    signature TEXT,
    docstring TEXT,
    UNIQUE(file_id, qualified_name, kind, start_line)
);

CREATE INDEX IF NOT EXISTS idx_symbols_project_name
    ON symbols(project_id, qualified_name);
CREATE INDEX IF NOT EXISTS idx_symbols_file
    ON symbols(file_id);

CREATE TABLE IF NOT EXISTS relations (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'deterministic',
    UNIQUE(source_type, source_id, relation_type, target_type, target_id)
);

CREATE INDEX IF NOT EXISTS idx_relations_source
    ON relations(project_id, source_type, source_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_relations_target
    ON relations(project_id, target_type, target_id, relation_type);

CREATE TABLE IF NOT EXISTS operation_log (
    operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    agent TEXT NOT NULL,
    project_id TEXT,
    action TEXT NOT NULL,
    target TEXT,
    reason TEXT,
    result TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS token_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    agent TEXT NOT NULL,
    project_id TEXT,
    task TEXT,
    purpose TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    context_sources TEXT NOT NULL DEFAULT '[]',
    result TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_log (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    project_id TEXT,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    alternatives TEXT NOT NULL,
    uncertainty TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS change_log (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    project_id TEXT,
    task TEXT,
    file_path TEXT NOT NULL,
    before_hash TEXT,
    after_hash TEXT,
    test_result TEXT NOT NULL,
    decision_id INTEGER,
    FOREIGN KEY(decision_id) REFERENCES decision_log(decision_id)
);

CREATE TABLE IF NOT EXISTS gateway_usage (
    session_id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    request_count INTEGER NOT NULL DEFAULT 0,
    read_count INTEGER NOT NULL DEFAULT 0,
    token_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(session_id, project_id)
);

CREATE TABLE IF NOT EXISTS gateway_sessions (
    session_id TEXT PRIMARY KEY,
    max_total_tokens INTEGER NOT NULL,
    max_files INTEGER NOT NULL,
    max_read_operations INTEGER NOT NULL,
    max_single_file_tokens INTEGER NOT NULL,
    max_request_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gateway_file_usage (
    session_id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    file_id TEXT NOT NULL REFERENCES files(file_id),
    PRIMARY KEY(session_id, project_id, file_id)
);

CREATE TABLE IF NOT EXISTS semantic_problems (
    problem_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    definition TEXT NOT NULL,
    formalization TEXT NOT NULL,
    constraints TEXT NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance = 'Human'),
    state TEXT NOT NULL CHECK (state IN ('proposed', 'active', 'modified', 'deprecated')),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS semantic_goals (
    goal_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance IN ('Human', 'AI', 'System')),
    state TEXT NOT NULL CHECK (state IN ('proposed', 'active', 'modified', 'deprecated')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS semantic_modules (
    module_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    function TEXT NOT NULL,
    primary_goal_id TEXT NOT NULL REFERENCES semantic_goals(goal_id),
    provenance TEXT NOT NULL CHECK (provenance IN ('Human', 'AI', 'System')),
    state TEXT NOT NULL CHECK (state IN ('proposed', 'active', 'modified', 'deprecated')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS semantic_implementations (
    implementation_id TEXT PRIMARY KEY,
    reference_type TEXT NOT NULL CHECK (reference_type IN ('file', 'symbol', 'runtime', 'other')),
    reference_id TEXT NOT NULL,
    project_id TEXT REFERENCES projects(project_id),
    observed_meaning TEXT NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance = 'System'),
    state TEXT NOT NULL CHECK (state IN ('proposed', 'active', 'modified', 'deprecated')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS semantic_relations (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK (source_type IN ('problem', 'goal', 'module', 'implementation')),
    source_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('problem', 'goal', 'module', 'implementation')),
    target_id TEXT NOT NULL,
    rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
    reason_trigger TEXT NOT NULL CHECK (length(trim(reason_trigger)) > 0),
    reason_gap TEXT NOT NULL CHECK (length(trim(reason_gap)) > 0),
    reason_response TEXT NOT NULL CHECK (length(trim(reason_response)) > 0),
    provenance TEXT NOT NULL CHECK (provenance IN ('Human', 'AI', 'System')),
    state TEXT NOT NULL CHECK (state IN ('proposed', 'active', 'modified', 'deprecated')),
    supersedes_relation_id INTEGER REFERENCES semantic_relations(relation_id),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE(source_type, source_id, relation_type, target_type, target_id, state)
);

CREATE INDEX IF NOT EXISTS idx_semantic_relations_source
    ON semantic_relations(source_type, source_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_semantic_relations_target
    ON semantic_relations(target_type, target_id, relation_type);

CREATE TABLE IF NOT EXISTS semantic_annotations (
    annotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type TEXT NOT NULL CHECK (object_type IN ('problem', 'goal', 'module', 'implementation')),
    object_id TEXT NOT NULL,
    meaning TEXT NOT NULL,
    engineering_problem TEXT NOT NULL DEFAULT '',
    engineering_goal TEXT NOT NULL DEFAULT '',
    mathematical_problem TEXT NOT NULL DEFAULT '',
    origin_type TEXT NOT NULL,
    origin_id TEXT,
    reason_trigger TEXT NOT NULL DEFAULT '',
    reason_gap TEXT NOT NULL DEFAULT '',
    reason_response TEXT NOT NULL DEFAULT '',
    provenance TEXT NOT NULL CHECK (provenance IN ('Human', 'AI', 'System')),
    state TEXT NOT NULL CHECK (state IN ('proposed', 'active', 'modified', 'deprecated')),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_semantic_annotations_object
    ON semantic_annotations(object_type, object_id, state);

CREATE TABLE IF NOT EXISTS semantic_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance IN ('Human', 'AI', 'System')),
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(object_type, object_id, version)
);

CREATE TABLE IF NOT EXISTS semantic_drift (
    drift_id INTEGER PRIMARY KEY AUTOINCREMENT,
    implementation_id TEXT NOT NULL REFERENCES semantic_implementations(implementation_id),
    declared_meaning TEXT NOT NULL,
    observed_meaning TEXT NOT NULL,
    evidence TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('review_required', 'accepted', 'rejected')),
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS semantic_problem_no_update
BEFORE UPDATE ON semantic_problems BEGIN SELECT RAISE(ABORT, 'mathematical problem requires human confirmation'); END;
CREATE TRIGGER IF NOT EXISTS semantic_problem_no_delete
BEFORE DELETE ON semantic_problems BEGIN SELECT RAISE(ABORT, 'mathematical problem history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS semantic_history_no_update
BEFORE UPDATE ON semantic_history BEGIN SELECT RAISE(ABORT, 'semantic history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS semantic_history_no_delete
BEFORE DELETE ON semantic_history BEGIN SELECT RAISE(ABORT, 'semantic history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS semantic_relations_no_update
BEFORE UPDATE ON semantic_relations BEGIN SELECT RAISE(ABORT, 'semantic relations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS semantic_relations_no_delete
BEFORE DELETE ON semantic_relations BEGIN SELECT RAISE(ABORT, 'semantic relations are append-only'); END;

CREATE TRIGGER IF NOT EXISTS operation_log_no_update
BEFORE UPDATE ON operation_log BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS operation_log_no_delete
BEFORE DELETE ON operation_log BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS decision_log_no_update
BEFORE UPDATE ON decision_log BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS decision_log_no_delete
BEFORE DELETE ON decision_log BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS change_log_no_update
BEFORE UPDATE ON change_log BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS change_log_no_delete
BEFORE DELETE ON change_log BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS token_audit_no_update
BEFORE UPDATE ON token_audit BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS token_audit_no_delete
BEFORE DELETE ON token_audit BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
"""

SCHEMA_VERSION = "4"


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
        if existing_version is not None and existing_version["value"] in {"2", "3"}:
            self.connection.execute(
                "UPDATE metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION,)
            )
            existing_version = None
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
        self.connection.set_authorizer(self._authorize_audit_tables)

    @staticmethod
    def _authorize_audit_tables(
        action: int, arg1: str | None, arg2: str | None,
        database: str | None, trigger: str | None,
    ) -> int:
        """在本连接上禁止审计表 UPDATE/DELETE；INSERT 仍由审计写入器使用。"""

        if action in {sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE} and arg1 in {
            "operation_log", "decision_log", "change_log", "token_audit",
        }:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

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

