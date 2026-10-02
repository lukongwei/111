"""Python AST symbol indexing."""

from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path
import sqlite3


def _symbol_id(file_id: str, qualified_name: str, kind: str, start_line: int) -> str:
    digest = sha256(f"{file_id}:{qualified_name}:{kind}:{start_line}".encode()).hexdigest()[:12]
    return f"S-{digest}"


class PythonSymbolIndexer:
    """Parse Python files with the standard-library AST and persist symbols."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def index_project(self, project_id: str, root: Path) -> dict[str, int]:
        files = self.connection.execute(
            "SELECT file_id, current_path FROM files WHERE project_id = ? "
            "AND status = 'active' AND language = 'python' ORDER BY current_path",
            (project_id,),
        ).fetchall()
        self.connection.execute("DELETE FROM symbols WHERE project_id = ?", (project_id,))
        inserted = 0
        failed = 0
        for file in files:
            path = root / Path(file["current_path"])
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(path))
            except (OSError, SyntaxError):
                failed += 1
                continue
            symbols = list(self._walk_symbols(tree, file["file_id"]))
            for symbol in symbols:
                self.connection.execute(
                    "INSERT INTO symbols(symbol_id, file_id, project_id, parent_symbol_id, name, "
                    "qualified_name, kind, language, start_line, end_line, signature, docstring) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'python', ?, ?, ?, ?) ",
                    (
                        symbol["symbol_id"], file["file_id"], project_id, symbol["parent_symbol_id"],
                        symbol["name"], symbol["qualified_name"], symbol["kind"],
                        symbol["start_line"], symbol["end_line"], symbol["signature"], symbol["docstring"],
                    ),
                )
                inserted += 1
        return {"files": len(files), "symbols": inserted, "failed_files": failed}

    def _walk_symbols(self, tree: ast.AST, file_id: str):
        def walk(nodes, parent_symbol_id=None, parent_names=()):
            for node in nodes:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    qualified = ".".join((*parent_names, node.name))
                    symbol_id = _symbol_id(file_id, qualified, kind, node.lineno)
                    yield {
                        "symbol_id": symbol_id,
                        "parent_symbol_id": parent_symbol_id,
                        "name": node.name,
                        "qualified_name": qualified,
                        "kind": kind,
                        "start_line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                        "signature": self._signature(node),
                        "docstring": ast.get_docstring(node),
                    }
                    yield from walk(node.body, symbol_id, (*parent_names, node.name))
                elif isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                    yield from walk(ast.iter_child_nodes(node), parent_symbol_id, parent_names)
        yield from walk(getattr(tree, "body", []))

    @staticmethod
    def _signature(node: ast.AST) -> str | None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                arguments = ast.unparse(node.args)
                return f"{node.name}({arguments})"
            except (AttributeError, ValueError):
                return node.name
        return None

