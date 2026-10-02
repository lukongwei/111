"""加载 Phase 0 的最小运行配置。

Phase 0 不引入 TOML 第三方依赖。Python 3.11+ 的标准库 `tomllib` 足以读取
配置文件；后续阶段再根据配置复杂度决定是否需要更强的校验层。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class WorkspaceConfig:
    """Workspace 的启动配置。

    输入：项目根目录和 TOML 配置路径。
    输出：只读的运行配置。
    副作用：读取配置文件，不修改文件系统。
    """

    root: Path
    name: str
    phase: int
    projects_dir: Path
    logs_dir: Path
    tasks_dir: Path
    allow_direct_filesystem_access: bool
    gateway_required: bool


def load_config(root: Path | str) -> WorkspaceConfig:
    """从 Workspace 根目录加载配置，并解析相对目录。

    配置文件不存在或内容不完整时直接失败，避免使用静默的错误默认值启动。
    """

    workspace_root = Path(root).resolve()
    config_path = workspace_root / "config" / "system.toml"
    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)

    workspace = raw["workspace"]
    paths = raw["paths"]
    runtime = raw["runtime"]

    return WorkspaceConfig(
        root=workspace_root,
        name=workspace["name"],
        phase=workspace["phase"],
        projects_dir=workspace_root / paths["projects"],
        logs_dir=workspace_root / paths["logs"],
        tasks_dir=workspace_root / paths["tasks"],
        allow_direct_filesystem_access=runtime["allow_direct_filesystem_access"],
        gateway_required=runtime["gateway_required"],
    )

