"""AI Workspace MVP 启动检查入口。"""

from __future__ import annotations

from pathlib import Path

from CORE.common.config import load_config


def main() -> int:
    """加载配置并输出当前模块状态。"""

    root = Path(__file__).resolve().parents[2]
    config = load_config(root)
    print(f"{config.name} MVP Phase {config.phase} baseline ready")
    print(f"root={config.root}")
    print(f"index_database={config.index_database}")
    print("filesystem_index=available (local management API)")
    print("gateway=available (agent access boundary)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

