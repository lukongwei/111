"""收集文件元数据和内容 Hash。

该模块只做确定性计算，不理解文件内容的语义，也不依赖 LLM。
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path


LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".txt": "text",
}


def detect_language(path: Path) -> str | None:
    """按扩展名确定性识别语言；未知扩展名返回 ``None``。"""

    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower())


def calculate_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """分块计算文件 SHA-256，避免把整个文件一次性读入内存。"""

    digest = sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()

