"""Small standard-library HTTP dashboard for local inspection."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse

from CORE.common.config import load_config
from CORE.index import IndexDatabase
from .service import DashboardService


def make_handler(workspace_root: Path, database_path: Path | None = None):
    config_path = workspace_root / "config" / "system.toml"
    config = load_config(workspace_root) if config_path.exists() else None
    index_database = database_path or (config.index_database if config else workspace_root / "index.sqlite3")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP API name
            route = urlparse(self.path).path
            with IndexDatabase(index_database) as database:
                dashboard = DashboardService(database.connection)
                if route == "/api/overview":
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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def serve(workspace_root: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(workspace_root))
    print(f"Dashboard listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

