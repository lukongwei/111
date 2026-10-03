"""End-to-end tests for Search, Symbols, Relations, Gateway and Context."""

from pathlib import Path
from http.client import HTTPConnection
import json
import tempfile
from threading import Thread
import unittest
from http.server import ThreadingHTTPServer

from CORE.audit import AuditService
from CORE.context import ContextEngine
from CORE.gateway import ContextGateway
from CORE.index import IndexDatabase, IndexService
from CORE.maintenance import MaintenanceService
from CORE.protocol import ContextBudget, GatewayRequest
from DASHBOARD.backend import DashboardService
from DASHBOARD.backend.server import make_handler
from DASHBOARD.backend.server import serve
from CORE.adapter import AgentAdapter, AgentRequest


class PlatformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project_root = self.root / "project"
        self.project_root.mkdir()
        (self.project_root / "app.py").write_text(
            "class Engine:\n    def run(self):\n        return helper()\n\ndef helper():\n    return 'interest score'\n",
            encoding="utf-8",
        )
        (self.project_root / "test_app.py").write_text(
            "from app import Engine\n\ndef test_engine():\n    return Engine().run()\n",
            encoding="utf-8",
        )
        (self.project_root / ".env").write_text("SECRET=hidden", encoding="utf-8")
        for name in ("credentials.json", "api_key.txt", "private.pem", "passwords.json", "secret.yaml", "token.txt"):
            (self.project_root / name).write_text("SECRET=hidden", encoding="utf-8")
        self.db = IndexDatabase(self.root / "index.sqlite3")
        self.index = IndexService(self.db)
        self.project = self.index.register_project("project", self.project_root)
        self.index.scan_project(self.project.project_id)
        self.index.index_code(self.project.project_id)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_search_symbols_and_relations(self) -> None:
        hits = self.index.search(self.project.project_id, "interest score", mode="text")
        self.assertEqual(hits[0].path, "app.py")
        symbols = self.index.list_symbols(self.project.project_id, "Engine")
        self.assertGreaterEqual(len(symbols), 2)
        self.assertIn("class", {item["kind"] for item in symbols})
        self.assertIn("function", {item["kind"] for item in symbols})
        class_symbol = next(item for item in symbols if item["qualified_name"] == "Engine")
        relations = self.index.relate(self.project.project_id, class_symbol["symbol_id"])
        self.assertTrue(any(item["relation_type"] == "contains" for item in relations))

    def test_search_modes_and_protocol_validation(self) -> None:
        self.assertTrue(self.index.search(self.project.project_id, "app.py", mode="name"))
        self.assertTrue(self.index.search(self.project.project_id, "app", mode="path"))
        self.assertTrue(self.index.search(self.project.project_id, "python", mode="metadata"))
        gateway = ContextGateway(self.index)
        invalid = gateway.handle({"op": "search", "project_id": self.project.project_id, "unknown": True})
        self.assertFalse(invalid.ok)
        self.assertIn("未知字段", invalid.error)

    def test_gateway_reads_symbols_and_rejects_sensitive_and_cross_project(self) -> None:
        gateway = ContextGateway(self.index, ContextBudget(max_single_file_tokens=100))
        symbol = self.index.list_symbols(self.project.project_id, "Engine")[0]
        read = gateway.handle(GatewayRequest("read", self.project.project_id, agent="tester", id=symbol["symbol_id"]))
        self.assertTrue(read.ok)
        self.assertIn("class Engine", read.data["content"])
        sensitive_file = next(file for file in self.index.list_files(self.project.project_id) if file.current_path == ".env")
        denied = gateway.handle(GatewayRequest("read", self.project.project_id, agent="tester", id=sensitive_file.file_id))
        self.assertFalse(denied.ok)
        self.assertIn("敏感", denied.error)
        foreign = gateway.handle(GatewayRequest("describe", "P-999999", agent="tester", id=symbol["symbol_id"]))
        self.assertFalse(foreign.ok)

        for filename in ("credentials.json", "api_key.txt", "private.pem", "passwords.json", "secret.yaml", "token.txt"):
            file = next(item for item in self.index.list_files(self.project.project_id) if item.current_path == filename)
            denied_variant = gateway.handle(GatewayRequest("read", self.project.project_id, agent="tester", id=file.file_id))
            self.assertFalse(denied_variant.ok, filename)

    def test_history_cross_project_and_deleted_file_are_rejected(self) -> None:
        other_root = self.root / "other"
        other_root.mkdir()
        (other_root / "other.txt").write_text("other", encoding="utf-8")
        other = self.index.register_project("other", other_root)
        self.index.scan_project(other.project_id)
        own_file = next(file for file in self.index.list_files(self.project.project_id) if file.current_path == "app.py")
        with self.assertRaises(KeyError):
            self.index.history(other.project_id, own_file.file_id)

        deleted_path = self.project_root / "deleted.txt"
        deleted_path.write_text("gone", encoding="utf-8")
        self.index.scan_project(self.project.project_id)
        deleted_file = next(file for file in self.index.list_files(self.project.project_id) if file.current_path == "deleted.txt")
        deleted_path.unlink()
        self.index.scan_project(self.project.project_id)
        gateway = ContextGateway(self.index)
        denied = gateway.handle(GatewayRequest("read", self.project.project_id, id=deleted_file.file_id))
        self.assertFalse(denied.ok)
        related = gateway.handle(GatewayRequest("relate", self.project.project_id, id=deleted_file.file_id))
        self.assertFalse(related.ok)

    def test_stale_file_id_cannot_read_replaced_content_before_rescan(self) -> None:
        file = next(item for item in self.index.list_files(self.project.project_id) if item.current_path == "app.py")
        (self.project_root / "app.py").write_text("new secret content", encoding="utf-8")
        gateway = ContextGateway(self.index)
        denied = gateway.handle(GatewayRequest("read", self.project.project_id, id=file.file_id))
        self.assertFalse(denied.ok)
        self.assertIn("重新索引", denied.error)

    def test_gateway_budget_and_context_engine(self) -> None:
        gateway = ContextGateway(self.index, ContextBudget(max_read_operations=1, max_single_file_tokens=1000))
        readable_files = [file for file in self.index.list_files(self.project.project_id) if file.current_path == "app.py"]
        readable_files.append(next(file for file in self.index.list_files(self.project.project_id) if file.current_path == "test_app.py"))
        first = gateway.handle(GatewayRequest("read", self.project.project_id, agent="limited", id=readable_files[0].file_id))
        second = gateway.handle(GatewayRequest("read", self.project.project_id, agent="limited", id=readable_files[1].file_id))
        self.assertTrue(first.ok)
        self.assertFalse(second.ok)
        context_db = IndexDatabase(self.root / "context.sqlite3")
        try:
            context_index = IndexService(context_db)
            context_project = context_index.register_project("project", self.project_root)
            context_index.scan_project(context_project.project_id)
            context_index.index_code(context_project.project_id)
            engine = ContextEngine(ContextGateway(
                context_index, ContextBudget(max_read_operations=4, max_single_file_tokens=1000)
            ))
            package = engine.assemble(context_project.project_id, "interest score", agent="engine")
            self.assertTrue(package.items)
            self.assertLessEqual(package.total_tokens, 8000)
        finally:
            context_db.close()

    def test_audit_dashboard_and_maintenance(self) -> None:
        audit = AuditService(self.db.connection)
        decision_id = audit.decision(self.project.project_id, "use deterministic ranking", "reproducible", ["embedding"], "ranking can evolve")
        audit.change(self.project.project_id, "test", "app.py", None, "hash", "passed", decision_id)
        audit.token("tester", self.project.project_id, "task", "testing", 10, 20, 0, ["F-000001"], "ok")
        dashboard = DashboardService(self.db.connection)
        overview = dashboard.overview()
        self.assertEqual(overview["projects"], 1)
        self.assertEqual(overview["token_total"], 30)
        self.assertEqual(MaintenanceService(self.db.connection).check(), [])

    def test_dashboard_http_and_agent_adapter(self) -> None:
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(self.root, self.root / "index.sqlite3")
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            connection.request("GET", "/api/overview")
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["projects"], 1)
            connection.request("GET", "/missing")
            missing = connection.getresponse()
            self.assertEqual(missing.status, 404)
            connection.close()
        finally:
            server.shutdown()
            server.server_close()

        adapter = AgentAdapter(ContextEngine(ContextGateway(self.index)))
        received = adapter.run(
            AgentRequest("mock", self.project.project_id, "interest score"),
            lambda payload: payload,
        )
        self.assertEqual(received["project_id"], self.project.project_id)
        self.assertTrue(received["context"])

    def test_dashboard_rejects_non_loopback_binding(self) -> None:
        with self.assertRaises(ValueError):
            serve(self.root, "0.0.0.0", 0)


if __name__ == "__main__":
    unittest.main()
