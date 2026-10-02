"""Workspace 配置与模块边界回归测试。"""

from pathlib import Path
import unittest

from CORE.common.config import load_config


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceTests(unittest.TestCase):
    def test_phase_one_configuration_loads_without_creating_index_database(self) -> None:
        config = load_config(ROOT)

        self.assertEqual(config.name, "AI Workspace")
        self.assertEqual(config.phase, 1)
        self.assertFalse(config.allow_direct_filesystem_access)
        self.assertTrue(config.gateway_required)
        self.assertEqual(config.index_database, ROOT / "DASHBOARD" / "data" / "index.sqlite3")

    def test_core_module_boundaries_remain_present(self) -> None:
        for relative_path in (
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
        ):
            with self.subTest(relative_path=relative_path):
                self.assertTrue((ROOT / relative_path).is_dir())


if __name__ == "__main__":
    unittest.main()
