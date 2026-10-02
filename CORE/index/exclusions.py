"""Filesystem Index 的默认忽略规则。"""

from __future__ import annotations

from pathlib import Path


DEFAULT_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

DEFAULT_IGNORED_FILES = frozenset({".coverage"})


def should_ignore_directory(path: Path) -> bool:
    """判断目录名是否属于系统默认忽略目录。"""

    return path.name in DEFAULT_IGNORED_DIRECTORIES


def should_ignore_file(path: Path) -> bool:
    """判断文件名是否属于系统默认忽略文件。"""

    return path.name in DEFAULT_IGNORED_FILES

