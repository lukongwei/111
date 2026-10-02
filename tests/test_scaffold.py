"""Phase 0 工程骨架验收测试。"""

from pathlib import Path
import unittest

from CORE.common.config import load_config


ROOT = Path(__file__).resolve().parents[1]


class ScaffoldTests(unittest.TestCase):
    def test_configuration_loads_from_workspace_root(self) -> None:
        config = load_config(ROOT)

        self.assertEqual(config.name, "AI Workspace")
        self.assertEqual(config.phase, 0)
        self.assertFalse(config.allow_direct_filesystem_access)
        self.assertTrue(config.gateway_required)
        self.assertEqual(config.projects_dir, ROOT / "PROJECTS")

    def test_required_module_boundaries_exist(self) -> None:
        required = [
            "_SYSTEM",
            "CORE/index",
            "CORE/context",
            "CORE/gateway",
            "CORE/protocol",
            "CORE/common",
            "PROJECTS/_template/.context",
            "DASHBOARD/backend",
            "DASHBOARD/frontend",
            "DASHBOARD/data",
            "LOGS",
            "TASKS",
        ]

        for relative_path in required:
            with self.subTest(relative_path=relative_path):
                self.assertTrue((ROOT / relative_path).is_dir())

    def test_phase_zero_does_not_claim_index_or_gateway_implementation(self) -> None:
        self.assertFalse((ROOT / "CORE" / "index" / "indexer.py").exists())
        self.assertFalse((ROOT / "CORE" / "gateway" / "server.py").exists())


if __name__ == "__main__":
    unittest.main()

