# AI Workspace

AI Workspace 是一个本地 AI Workspace 骨架，目标是让多个 LLM / Agent 通过统一的 Context Gateway 共享受控的本地信息基础设施。

当前版本是 **Phase 0：工程骨架**。本阶段只提供可启动的工程结构、配置系统、测试框架和基础文档，不实现文件索引、搜索、AST、权限执行或 Context 组装。

## 快速开始

要求：Python 3.11 或更高版本。当前实现只使用 Python 标准库。

```powershell
python -m unittest discover -s tests -v
python -m core.common.app
```

## 目录

```text
AI_WORKSPACE/
├── _SYSTEM/                 系统宪法、协议和文件规则
├── CORE/                    核心运行时模块边界
│   ├── index/               Index 占位，后续负责确定性信息定位
│   ├── context/             Context Engine 占位，后续负责上下文组装
│   ├── gateway/             Context Gateway 占位，后续负责唯一访问入口
│   ├── protocol/            结构化请求协议占位
│   └── common/              配置、启动入口等公共基础设施
├── PROJECTS/                共享项目目录和项目模板
├── DASHBOARD/               中央 Dashboard 目录
├── LOGS/                    Append-only 日志目录
├── TASKS/                   Task 记录目录
├── config/                  系统配置
├── tests/                   自动化测试
└── pyproject.toml           Python 工程元数据
```

## 技术栈

- Python 3.11+：核心运行时和测试框架
- Python `unittest`：Phase 0 测试框架，避免无明确收益的第三方依赖
- SQLite：计划在 Phase 1 用于 Index 持久化；Phase 0 不创建 schema
- Git：代码版本、分支和初始提交管理
- 未来的全文搜索、AST、Git 状态和 Gateway 均通过 CORE 内部模块实现，LLM 不直接接触文件系统

## 开发阶段

详见 [`_SYSTEM/CONSTITUTION.md`](_SYSTEM/CONSTITUTION.md) 和 [`_SYSTEM/AGENT_PROTOCOL.md`](_SYSTEM/AGENT_PROTOCOL.md)。未经确认，不进入 Phase 1。

