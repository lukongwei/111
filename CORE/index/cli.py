"""Filesystem Index 的本地管理命令。"""

from __future__ import annotations

import argparse
from pathlib import Path

from CORE.common.config import load_config
from CORE.index import IndexDatabase, IndexService


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the AI Workspace filesystem index")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register", help="Register a project for indexing")
    register.add_argument("name")
    register.add_argument("path", type=Path)

    scan = subparsers.add_parser("scan", help="Scan a registered project")
    scan.add_argument("project_id")

    subparsers.add_parser("projects", help="List registered projects")
    args = parser.parse_args()
    workspace = load_config(Path(__file__).resolve().parents[2])

    with IndexDatabase(workspace.index_database) as database:
        service = IndexService(database)
        if args.command == "register":
            project = service.register_project(args.name, args.path)
            print(f"{project.project_id}\t{project.name}\t{project.root_path}")
        elif args.command == "scan":
            result = service.scan_project(args.project_id)
            print(
                f"{result.status}: scanned={result.scanned_count} added={result.added_count} "
                f"changed={result.changed_count} moved={result.moved_count} "
                f"deleted={result.deleted_count} warnings={result.warning_count}"
            )
            if result.error_message:
                print(result.error_message)
            return 0 if result.status == "completed" else 1
        else:
            rows = database.connection.execute(
                "SELECT project_id, name, root_path FROM projects ORDER BY project_id"
            ).fetchall()
            for row in rows:
                print(f"{row['project_id']}\t{row['name']}\t{row['root_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

