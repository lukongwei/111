"""Filesystem Index 的 Phase 1 验收测试。"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from CORE.index import IndexDatabase, IndexService


class IndexServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project_root = self.root / "project"
        self.project_root.mkdir()
        self.database = IndexDatabase(self.root / "index.sqlite3")
        self.service = IndexService(self.database)
        self.project = self.service.register_project("sample", self.project_root)

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def write(self, relative_path: str, content: str) -> Path:
        path = self.project_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_initial_scan_records_files_metadata_and_directory_tree(self) -> None:
        self.write("src/main.py", "print('hello')\n")
        self.write("README.md", "sample\n")

        result = self.service.scan_project(self.project.project_id)

        self.assertEqual(result.status, "completed")
        self.assertEqual((result.scanned_count, result.added_count), (2, 2))
        files = self.service.list_files(self.project.project_id)
        self.assertEqual([file.file_id for file in files], ["F-000001", "F-000002"])
        python_file = next(file for file in files if file.current_path == "src/main.py")
        self.assertEqual(python_file.language, "python")
        self.assertEqual(python_file.file_type, ".py")
        self.assertEqual(len(python_file.content_hash), 64)
        self.assertIn("src", [item["relative_path"] for item in self.service.list_directories(self.project.project_id)])

    def test_unchanged_scan_recomputes_no_hash_and_preserves_ids(self) -> None:
        self.write("a.txt", "same")
        first = self.service.scan_project(self.project.project_id)
        file_id = self.service.list_files(self.project.project_id)[0].file_id

        second = self.service.scan_project(self.project.project_id)

        self.assertEqual(first.added_count, 1)
        self.assertEqual(second.hash_recomputed_count, 0)
        self.assertEqual(second.added_count + second.changed_count + second.moved_count + second.deleted_count, 0)
        self.assertEqual(self.service.list_files(self.project.project_id)[0].file_id, file_id)

    def test_unchanged_scan_does_not_write_file_rows(self) -> None:
        self.write("a.txt", "same")
        self.service.scan_project(self.project.project_id)
        self.database.connection.execute(
            "CREATE TABLE file_update_audit(file_id TEXT NOT NULL)"
        )
        self.database.connection.execute(
            "CREATE TRIGGER audit_file_update AFTER UPDATE ON files "
            "BEGIN INSERT INTO file_update_audit(file_id) VALUES (NEW.file_id); END"
        )
        self.database.connection.commit()

        result = self.service.scan_project(self.project.project_id)

        write_count = self.database.connection.execute(
            "SELECT COUNT(*) FROM file_update_audit"
        ).fetchone()[0]
        self.assertEqual(result.changed_count, 0)
        self.assertEqual(write_count, 0)

    def test_single_file_change_only_updates_that_file_row(self) -> None:
        first_path = self.write("a.txt", "first")
        self.write("b.txt", "second")
        self.service.scan_project(self.project.project_id)
        self.database.connection.execute(
            "CREATE TABLE file_update_audit(file_id TEXT NOT NULL)"
        )
        self.database.connection.execute(
            "CREATE TRIGGER audit_file_update AFTER UPDATE ON files "
            "BEGIN INSERT INTO file_update_audit(file_id) VALUES (NEW.file_id); END"
        )
        self.database.connection.commit()
        first_id = next(
            file.file_id for file in self.service.list_files(self.project.project_id)
            if file.current_path == "a.txt"
        )
        first_path.write_text("updated", encoding="utf-8")

        result = self.service.scan_project(self.project.project_id)

        written_ids = [row[0] for row in self.database.connection.execute(
            "SELECT file_id FROM file_update_audit"
        )]
        self.assertEqual(result.changed_count, 1)
        self.assertEqual(written_ids, [first_id])

    def test_modified_file_keeps_id_and_updates_hash(self) -> None:
        path = self.write("a.txt", "before")
        self.service.scan_project(self.project.project_id)
        before = self.service.list_files(self.project.project_id)[0]
        path.write_text("after and longer", encoding="utf-8")

        result = self.service.scan_project(self.project.project_id)
        after = self.service.list_files(self.project.project_id)[0]

        self.assertEqual(result.changed_count, 1)
        self.assertEqual(result.hash_recomputed_count, 1)
        self.assertEqual(after.file_id, before.file_id)
        self.assertNotEqual(after.content_hash, before.content_hash)

    def test_same_size_content_change_is_detected(self) -> None:
        path = self.write("a.txt", "aaaa")
        self.service.scan_project(self.project.project_id)
        before = self.service.list_files(self.project.project_id)[0]
        path.write_text("bbbb", encoding="utf-8")

        result = self.service.scan_project(self.project.project_id)

        self.assertEqual(result.changed_count, 1)
        self.assertNotEqual(self.service.get_file(before.file_id).content_hash, before.content_hash)

    def test_delete_retains_tombstone_and_reappearing_path_keeps_id(self) -> None:
        path = self.write("a.txt", "first")
        self.service.scan_project(self.project.project_id)
        file_id = self.service.list_files(self.project.project_id)[0].file_id
        path.unlink()

        deleted = self.service.scan_project(self.project.project_id)
        self.assertEqual(deleted.deleted_count, 1)
        self.assertEqual(self.service.list_files(self.project.project_id), [])
        self.assertEqual(self.service.get_file(file_id).status, "deleted")

        self.write("a.txt", "replacement")
        restored = self.service.scan_project(self.project.project_id)
        self.assertEqual(restored.changed_count, 1)
        self.assertEqual(self.service.list_files(self.project.project_id)[0].file_id, file_id)

    def test_move_with_identical_content_preserves_id_and_records_path_history(self) -> None:
        old_path = self.write("src/a.py", "value = 1\n")
        self.service.scan_project(self.project.project_id)
        file_id = self.service.list_files(self.project.project_id)[0].file_id
        new_path = self.project_root / "lib" / "a.py"
        new_path.parent.mkdir()
        old_path.rename(new_path)

        result = self.service.scan_project(self.project.project_id)

        self.assertEqual(result.moved_count, 1)
        self.assertEqual(result.added_count, 0)
        self.assertEqual(result.deleted_count, 0)
        file_record = self.service.get_file(file_id)
        self.assertEqual(file_record.current_path, "lib/a.py")
        paths = self.service.list_file_paths(file_id)
        self.assertEqual({item["relative_path"] for item in paths}, {"src/a.py", "lib/a.py"})
        self.assertEqual(sum(item["is_current"] for item in paths), 1)

    def test_multiple_moves_in_one_scan_do_not_conflict_on_active_paths(self) -> None:
        first = self.write("a.txt", "first")
        second = self.write("b.txt", "second")
        self.service.scan_project(self.project.project_id)
        original_ids = {file.current_path: file.file_id for file in self.service.list_files(self.project.project_id)}
        staging = self.project_root / "staging"
        staging.mkdir()
        first.rename(staging / "first.txt")
        second.rename(staging / "second.txt")
        (staging / "first.txt").rename(self.project_root / "c.txt")
        (staging / "second.txt").rename(self.project_root / "d.txt")
        staging.rmdir()

        result = self.service.scan_project(self.project.project_id)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.moved_count, 2)
        self.assertEqual(result.deleted_count, 0)
        current_ids = {file.current_path: file.file_id for file in self.service.list_files(self.project.project_id)}
        self.assertEqual(current_ids, {"c.txt": original_ids["a.txt"], "d.txt": original_ids["b.txt"]})

    def test_identical_files_get_distinct_ids_and_ambiguous_move_is_not_guessed(self) -> None:
        first = self.write("a.txt", "duplicate")
        self.write("b.txt", "duplicate")
        self.service.scan_project(self.project.project_id)
        old_ids = {file.current_path: file.file_id for file in self.service.list_files(self.project.project_id)}
        first.unlink()
        (self.project_root / "b.txt").unlink()
        self.write("c.txt", "duplicate")
        self.write("d.txt", "duplicate")

        result = self.service.scan_project(self.project.project_id)

        self.assertEqual(len(set(old_ids.values())), 2)
        self.assertEqual(result.moved_count, 0)
        self.assertEqual(result.added_count, 2)
        self.assertEqual(result.deleted_count, 2)
        self.assertEqual(result.warning_count, 2)
        self.assertTrue(all(item["warning_type"] == "ambiguous_move" for item in self.service.list_warnings(result.run_id)))

    def test_default_exclusions_and_symlinks_are_not_indexed(self) -> None:
        self.write("visible.txt", "yes")
        self.write(".git/config", "hidden")
        self.write("__pycache__/module.pyc", "hidden")
        try:
            (self.project_root / "linked.txt").symlink_to(self.project_root / "visible.txt")
        except OSError:
            self.skipTest("symbolic link creation is unavailable in this environment")

        result = self.service.scan_project(self.project.project_id)

        self.assertEqual([file.current_path for file in self.service.list_files(self.project.project_id)], ["visible.txt"])
        self.assertEqual(result.warning_count, 1)
        self.assertEqual(self.service.list_warnings(result.run_id)[0]["warning_type"], "symlink_skipped")

    def test_unreadable_file_fails_scan_without_partial_database_changes(self) -> None:
        self.write("a.txt", "stable")
        self.service.scan_project(self.project.project_id)
        original = self.service.list_files(self.project.project_id)
        self.write("b.txt", "new")

        with patch("CORE.index.service.calculate_sha256", side_effect=OSError("read failed")):
            result = self.service.scan_project(self.project.project_id)

        self.assertEqual(result.status, "failed")
        self.assertEqual(self.service.list_files(self.project.project_id), original)
        run = self.database.connection.execute(
            "SELECT status, error_message FROM index_runs WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        self.assertEqual(run["status"], "failed")
        self.assertIn("read failed", run["error_message"])

    def test_database_write_failure_rolls_back_partial_scan(self) -> None:
        self.write("existing.txt", "stable")
        self.service.scan_project(self.project.project_id)
        original = self.service.list_files(self.project.project_id)
        self.write("new.txt", "new")

        with patch.object(self.service, "_replace_directories", side_effect=OSError("write failed")):
            result = self.service.scan_project(self.project.project_id)

        self.assertEqual(result.status, "failed")
        self.assertEqual(self.service.list_files(self.project.project_id), original)
        run = self.database.connection.execute(
            "SELECT status, error_message FROM index_runs WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        self.assertEqual(run["status"], "failed")
        self.assertIn("write failed", run["error_message"])

    def test_project_registration_is_idempotent_and_requires_existing_directory(self) -> None:
        repeated = self.service.register_project("renamed", self.project_root)
        self.assertEqual(repeated.project_id, self.project.project_id)
        self.assertEqual(repeated.name, "sample")
        with self.assertRaises(FileNotFoundError):
            self.service.register_project("missing", self.root / "missing")

    def test_index_database_and_sqlite_sidecars_are_excluded_from_project_scan(self) -> None:
        workspace = self.root / "workspace"
        workspace.mkdir()
        (workspace / "source.py").write_text("x = 1\n", encoding="utf-8")
        database = IndexDatabase(workspace / "index.sqlite3")
        try:
            service = IndexService(database)
            project = service.register_project("workspace", workspace)
            result = service.scan_project(project.project_id)
            self.assertEqual(result.scanned_count, 1)
            self.assertEqual([file.current_path for file in service.list_files(project.project_id)], ["source.py"])
        finally:
            database.close()


if __name__ == "__main__":
    unittest.main()
