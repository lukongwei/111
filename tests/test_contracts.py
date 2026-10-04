"""Final cross-module contract checks."""

from pathlib import Path
import tempfile
import unittest
import sqlite3

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
                self.assertEqual(version, "4")
                database.connection.execute(
                    "UPDATE metadata SET value = '3' WHERE key = 'schema_version'"
                )
                database.connection.commit()
            with IndexDatabase(path) as migrated:
                version = migrated.connection.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()[0]
                self.assertEqual(version, "4")
                self.assertIsNotNone(migrated.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'semantic_problems'"
                ).fetchone())
                migrated.connection.execute(
                    "UPDATE metadata SET value = '999' WHERE key = 'schema_version'"
                )
                migrated.connection.commit()
            with self.assertRaises(RuntimeError):
                IndexDatabase(path)

    def test_semantic_problem_is_human_owned_and_immutable(self) -> None:
        from CORE.semantic import SemanticService

        with tempfile.TemporaryDirectory() as directory:
            with IndexDatabase(Path(directory) / "index.sqlite3") as database:
                semantic = SemanticService(database)
                with self.assertRaises(PermissionError):
                    semantic.create_problem("P", "definition", human="AI")
                problem = semantic.create_problem("P", "definition", "formal", "constraints")
                with self.assertRaises(Exception):
                    database.connection.execute(
                        "UPDATE semantic_problems SET definition = 'changed' WHERE problem_id = ?",
                        (problem.object_id,),
                    )
                database.connection.rollback()
                history = semantic.history("problem", problem.object_id)
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]["provenance"], "Human")

    def test_semantic_module_requires_goal_and_relations_require_rationale(self) -> None:
        from CORE.semantic import SemanticService

        with tempfile.TemporaryDirectory() as directory:
            with IndexDatabase(Path(directory) / "index.sqlite3") as database:
                semantic = SemanticService(database)
                goal = semantic.create_goal("Locate context", "Keep context selection inexpensive")
                with self.assertRaises(ValueError):
                    semantic.relate(
                        "goal", goal.object_id, "supports", "goal", goal.object_id,
                        "", "trigger", "gap", "response",
                    )
                with self.assertRaises(ValueError):
                    semantic.relate(
                        "goal", goal.object_id, "implements", "module", goal.object_id,
                        "rationale", "trigger", "gap", "response",
                    )
                with self.assertRaises(KeyError):
                    semantic.create_module(
                        "Index", "Build an index", "G-999999", "implements", "trigger", "gap", "response",
                    )
                module = semantic.create_module(
                    "Index", "Build an index", goal.object_id,
                    "The index makes information locatable", "task exists", "raw files are costly", "index metadata",
                )
                relations = semantic.relations_for("module", module.object_id)
                self.assertEqual(len(relations), 1)
                self.assertEqual(relations[0].relation_type, "implements")

    def test_semantic_drift_is_review_required_and_history_is_append_only(self) -> None:
        from CORE.semantic import SemanticService

        with tempfile.TemporaryDirectory() as directory:
            with IndexDatabase(Path(directory) / "index.sqlite3") as database:
                semantic = SemanticService(database)
                implementation = semantic.create_implementation("runtime", "runtime-1", "indexed file facts")
                drift_id = semantic.record_drift(
                    implementation.object_id, "indexed file facts", "runtime behavior", "implementation changed",
                )
                state = database.connection.execute(
                    "SELECT state FROM semantic_drift WHERE drift_id = ?", (drift_id,)
                ).fetchone()[0]
                self.assertEqual(state, "review_required")
                with self.assertRaises(Exception):
                    database.connection.execute("DELETE FROM semantic_history")

    def test_module_annotation_carries_the_semantic_chain(self) -> None:
        from CORE.semantic import SemanticService

        with tempfile.TemporaryDirectory() as directory:
            with IndexDatabase(Path(directory) / "index.sqlite3") as database:
                semantic = SemanticService(database)
                goal = semantic.create_goal("Locate context", "Keep context selection inexpensive")
                module = semantic.create_module(
                    "Index", "Build an index", goal.object_id,
                    "The index makes information locatable", "task exists", "raw files are costly", "index metadata",
                )
                with self.assertRaises(ValueError):
                    semantic.annotate("module", module.object_id, "index meaning")
                annotation_id = semantic.annotate(
                    "module", module.object_id, "index meaning",
                    engineering_problem="Information is hard to locate",
                    engineering_goal="Make information locatable",
                    mathematical_problem="Minimize context cost subject to sufficient information",
                    trigger="task requires targeted context",
                    gap="raw files are expensive to inspect",
                    response="use deterministic indexing",
                )
                self.assertGreater(annotation_id, 0)

    def test_semantic_revision_preserves_history_and_problem_cannot_be_revised(self) -> None:
        from CORE.semantic import SemanticService

        with tempfile.TemporaryDirectory() as directory:
            with IndexDatabase(Path(directory) / "index.sqlite3") as database:
                semantic = SemanticService(database)
                problem = semantic.create_problem("P", "definition")
                goal = semantic.create_goal("G", "old goal")
                with self.assertRaises(PermissionError):
                    semantic.revise("problem", problem.object_id, {"definition": "new"}, "AI", "agent", "adapt")
                semantic.revise("goal", goal.object_id, {"description": "new goal"}, "AI", "agent", "evidence changed")
                history = semantic.history("goal", goal.object_id)
                self.assertEqual(len(history), 3)
                self.assertIn("old goal", history[0]["snapshot"])
                self.assertIn("new goal", history[-1]["snapshot"])

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
