"""Filesystem Index 的公共数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectRecord:
    """已注册项目的身份和根目录。"""

    project_id: str
    name: str
    root_path: Path
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class FileRecord:
    """文件当前状态；`current_path` 始终是项目内相对路径。"""

    file_id: str
    project_id: str
    current_path: str
    file_name: str
    parent_path: str
    file_type: str | None
    language: str | None
    size: int
    content_hash: str
    modified_time_ns: int
    change_time_ns: int
    status: str
    first_seen_at: str
    last_seen_at: str
    deleted_at: str | None


@dataclass(frozen=True)
class ScanResult:
    """一次扫描的可审计结果。"""

    run_id: str
    project_id: str
    status: str
    scanned_count: int
    added_count: int
    changed_count: int
    moved_count: int
    deleted_count: int
    hash_recomputed_count: int
    warning_count: int
    error_message: str | None = None


@dataclass(frozen=True)
class SymbolRecord:
    """代码结构索引中的最小可读单元。"""

    symbol_id: str
    file_id: str
    project_id: str
    parent_symbol_id: str | None
    name: str
    qualified_name: str
    kind: str
    language: str
    start_line: int
    end_line: int
    signature: str | None
    docstring: str | None

