"""Final cross-module contract checks."""

from pathlib import Path
import tempfile
import unittest

from CORE.index import IndexDatabase
from CORE.protocol import GatewayRequest


class ContractTests(unittest.TestCase):
    def test_schema_version_is_explicit_and_rejects_unknown_existing_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.sqlite3"
            with IndexDatabase(path) as database:
                version = database.connection.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()[0]
                self.assertEqual(version, "2")
                database.connection.execute(
                    "UPDATE metadata SET value = '999' WHERE key = 'schema_version'"
                )
                database.connection.commit()
            with self.assertRaises(RuntimeError):
                IndexDatabase(path)

    def test_protocol_rejects_unknown_fields_and_bad_relation_shape(self) -> None:
        with self.assertRaises(ValueError):
            GatewayRequest.from_dict({"op": "status", "project_id": "P-1", "extra": True})
        with self.assertRaises(ValueError):
            GatewayRequest.from_dict({"op": "relate", "project_id": "P-1", "relation": "tests"})
        with self.assertRaises(ValueError):
            GatewayRequest.from_dict({"op": "status", "project_id": "P-1", "limit": True})


if __name__ == "__main__":
    unittest.main()
