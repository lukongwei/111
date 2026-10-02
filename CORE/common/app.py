"""AI Workspace Phase 0 启动检查入口。"""

from __future__ import annotations

from pathlib import Path

from CORE.common.config import load_config


def main() -> int:
    """加载配置并输出启动状态；不启动尚未实现的核心服务。"""

    root = Path(__file__).resolve().parents[2]
    config = load_config(root)
    print(f"{config.name} Phase {config.phase} ready")
    print(f"root={config.root}")
    print("index=not implemented (Phase 1)")
    print("gateway=not implemented (Phase 5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

