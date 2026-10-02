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

    def test_gateway_budget_and_context_engine(self) -> None:
        gateway = ContextGateway(self.index, ContextBudget(max_read_operations=1, max_single_file_tokens=1000))
        readable_files = [file for file in self.index.list_files(self.project.project_id) if file.current_path != ".env"]
        first = gateway.handle(GatewayRequest("read", self.project.project_id, agent="limited", id=readable_files[0].file_id))
        second = gateway.handle(GatewayRequest("read", self.project.project_id, agent="limited", id=readable_files[1].file_id))
        self.assertTrue(first.ok)
        self.assertFalse(second.ok)
        engine = ContextEngine(ContextGateway(self.index, ContextBudget(max_read_operations=4, max_single_file_tokens=1000)))
        package = engine.assemble(self.project.project_id, "interest score", agent="engine")
        self.assertTrue(package.items)
        self.assertLessEqual(package.total_tokens, 8000)
        self.assertTrue(any(item.reason.startswith("relation:") for item in package.items))

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


if __name__ == "__main__":
    unittest.main()
