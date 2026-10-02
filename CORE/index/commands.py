"""Unified local operator CLI for the workspace MVP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from CORE.audit import AuditService
from CORE.common.config import load_config
from CORE.context import ContextEngine
from CORE.gateway import ContextGateway
from CORE.index import IndexDatabase, IndexService
from CORE.maintenance import MaintenanceService
from CORE.protocol import ContextBudget, GatewayRequest


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Workspace operator CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register")
    register.add_argument("name")
    register.add_argument("path", type=Path)
    scan = sub.add_parser("scan")
    scan.add_argument("project_id")
    code = sub.add_parser("code")
    code.add_argument("project_id")
    search = sub.add_parser("search")
    search.add_argument("project_id")
    search.add_argument("query")
    search.add_argument("--mode", default="text", choices=["name", "path", "text", "metadata"])
    search.add_argument("--limit", type=int, default=10)
    request = sub.add_parser("request")
    request.add_argument("payload", help="JSON Gateway request")
    context = sub.add_parser("context")
    context.add_argument("project_id")
    context.add_argument("task")
    health = sub.add_parser("health")

    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    config = load_config(root)
    with IndexDatabase(config.index_database) as database:
        index = IndexService(database)
        if args.command == "register":
            _json(index.register_project(args.name, args.path).__dict__)
        elif args.command == "scan":
            _json(index.scan_project(args.project_id).__dict__)
        elif args.command == "code":
            _json(index.index_code(args.project_id))
        elif args.command == "search":
            _json([item.__dict__ for item in index.search(args.project_id, args.query, args.mode, args.limit)])
        elif args.command == "request":
            gateway = ContextGateway(index)
            response = gateway.handle(json.loads(args.payload))
            _json(response.as_dict())
        elif args.command == "context":
            engine = ContextEngine(ContextGateway(index))
            package = engine.assemble(args.project_id, args.task)
            _json({"task": package.task, "project_id": package.project_id,
                   "items": [item.__dict__ for item in package.items],
                   "total_tokens": package.total_tokens})
        elif args.command == "health":
            _json(MaintenanceService(database.connection).check())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

