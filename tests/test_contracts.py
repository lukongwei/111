"""Final cross-module contract checks."""

from pathlib import Path
import tempfile
import unittest

from CORE.index import IndexDatabase
from CORE.protocol import ContextBudget, GatewayRequest
from CORE.gateway import ContextGateway
from CORE.index import IndexService


class ContractTests(unittest.TestCase):
    def test_schema_version_is_explicit_and_rejects_unknown_existing_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.sqlite3"
            with IndexDatabase(path) as database:
                version = database.connection.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()[0]
                self.assertEqual(version, "3")
                database.connection.execute(
                    "UPDATE metadata SET value = '999' WHERE key = 'schema_version'"
                )
                database.connection.commit()
            with self.assertRaises(RuntimeError):
                IndexDatabase(path)

    def test_audit_tables_reject_update_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.sqlite3"
            with IndexDatabase(path) as database:
                database.connection.execute(
                    "INSERT INTO operation_log(timestamp, agent, action, result, detail) "
                    "VALUES ('now', 'test', 'check', 'ok', 'original')"
                )
                database.connection.commit()
                with self.assertRaises(Exception):
                    database.connection.execute("UPDATE operation_log SET detail = 'changed'")
                database.connection.rollback()
                with self.assertRaises(Exception):
                    database.connection.execute("DELETE FROM operation_log")

    def test_protocol_rejects_unknown_fields_and_bad_relation_shape(self) -> None:
        with self.assertRaises(ValueError):
            GatewayRequest.from_dict({"op": "status", "project_id": "P-1", "extra": True})
        with self.assertRaises(ValueError):
            GatewayRequest.from_dict({"op": "relate", "project_id": "P-1", "relation": "tests"})
        with self.assertRaises(ValueError):
            GatewayRequest.from_dict({"op": "status", "project_id": "P-1", "limit": True})

    def test_gateway_budget_policy_cannot_be_widened_for_same_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            (root / "a.txt").write_text("a", encoding="utf-8")
            database = IndexDatabase(Path(directory) / "index.sqlite3")
            try:
                index = IndexService(database)
                project = index.register_project("p", root)
                index.scan_project(project.project_id)
                ContextGateway(index, budget=ContextBudget(max_read_operations=1))
                with self.assertRaises(ValueError):
                    ContextGateway(index, budget=ContextBudget(max_read_operations=999))
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
