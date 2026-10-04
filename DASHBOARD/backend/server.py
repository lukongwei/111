"""Small standard-library HTTP dashboard for local inspection."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from CORE.common.config import load_config
from CORE.index import IndexDatabase, IndexService
from .console import ConsoleService
from .service import DashboardService


def make_handler(workspace_root: Path, database_path: Path | None = None):
    config_path = workspace_root / "config" / "system.toml"
    config = load_config(workspace_root) if config_path.exists() else None
    index_database = database_path or (config.index_database if config else workspace_root / "index.sqlite3")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP API name
            parsed = urlparse(self.path)
            route = parsed.path
            if route == "/":
                frontend = workspace_root / "DASHBOARD" / "frontend" / "index.html"
                if frontend.exists():
                    self._send_bytes(frontend.read_bytes(), "text/html; charset=utf-8")
                    return
            with IndexDatabase(index_database) as database:
                dashboard = DashboardService(database.connection)
                if route.startswith("/api/console/"):
                    payload = self._console_get(route, parse_qs(parsed.query), database)
                elif route == "/api/overview":
                    payload = dashboard.overview()
                elif route == "/api/projects":
                    payload = dashboard.projects()
                elif route == "/api/alerts":
                    payload = dashboard.alerts()
                elif route == "/":
                    payload = {
                        "name": config.name if config else "AI Workspace",
                        "phase": config.phase if config else None,
                        "endpoints": ["/api/overview", "/api/projects", "/api/alerts"],
                    }
                else:
                    self.send_error(404, "Not Found")
                    return
            self._send_json(payload)

        def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP API name
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/console/"):
                self.send_error(404, "Not Found")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                with IndexDatabase(index_database) as database:
                    service = ConsoleService(IndexService(database))
                    payload = self._console_post(parsed.path, body, service)
                self._send_json(payload)
            except (KeyError, ValueError, OSError, TypeError, json.JSONDecodeError) as error:
                self._send_json({"error": str(error)}, status=400)

        def _console_get(self, route: str, query: dict[str, list[str]], database: IndexDatabase) -> object:
            service = ConsoleService(IndexService(database))
            parts = [part for part in route.split("/") if part]
            if parts == ["api", "console", "projects"]:
                return {"projects": service.projects()}
            if len(parts) == 5 and parts[:3] == ["api", "console", "projects"] and parts[4] == "search":
                return {"results": service.search(
                    parts[3], query.get("query", [""])[0], query.get("mode", ["text"])[0],
                    int(query.get("limit", ["10"])[0]),
                )}
            if len(parts) == 6 and parts[:3] == ["api", "console", "projects"] and parts[4] == "objects":
                return service.object_detail(parts[3], parts[5])
            if len(parts) == 5 and parts[:3] == ["api", "console", "projects"] and parts[4] == "status":
                project_id = parts[3]
                return {"status": service.index.status(project_id), "counts": service._counts(project_id)}
            raise KeyError("Not Found")

        @staticmethod
        def _console_post(route: str, body: dict[str, object], service: ConsoleService) -> object:
            parts = [part for part in route.split("/") if part]
            if parts == ["api", "console", "projects"]:
                return service.register(str(body.get("name", "")), str(body.get("root_path", "")))
            if len(parts) == 5 and parts[:3] == ["api", "console", "projects"]:
                project_id, action = parts[3], parts[4]
                if action == "scan":
                    return service.scan(project_id)
                if action == "code":
                    return service.code_index(project_id)
                if action == "context":
                    return service.assemble_context(
                        project_id, str(body.get("task", "")), int(body.get("max_items", 8)),
                    )
            raise KeyError("Not Found")

        def _send_json(self, payload: object, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8", status)

        def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def serve(workspace_root: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Dashboard 默认只允许回环地址；远程访问需要单独的认证反向代理")
    server = ThreadingHTTPServer((host, port), make_handler(workspace_root))
    print(f"Dashboard listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
