# AI Workspace

AI Workspace 是本地 AI 信息基础设施，目标是让多个 LLM / Agent 通过统一的 Context Gateway 共享受控信息。

当前已完成 **Phase 1：Filesystem Index**。系统可注册项目、将文件元数据保存到 SQLite、执行确定性文件发现和增量更新，并识别唯一且内容未变的文件移动。

尚未实现全文搜索、AST / Symbol、Relation、Context Gateway、Context Engine、Agent Adapter 和 Dashboard Web 服务。Agent 不能直接调用 Index 或读取本地文件；这些能力须等待对应阶段实现。

## 快速开始

要求：Python 3.11 或更高版本。当前只使用 Python 标准库。

```powershell
python -m unittest discover -s tests -v
python -m CORE.common.app
python -m CORE.index.cli --help
```

## 注册并扫描项目

SQLite 默认位于 `DASHBOARD/data/index.sqlite3`。只扫描显式注册的项目，不跟随符号链接；默认排除 `.git`、虚拟环境、缓存、依赖和构建目录。删除记录保留为 tombstone，File ID 不复用。移动识别只在 SHA-256 对应唯一时执行。

```powershell
python -m CORE.index.cli register <项目名> <项目绝对路径>
python -m CORE.index.cli projects
python -m CORE.index.cli scan <项目ID>
```

CLI 是本地管理入口，不是 Agent 协议；Gateway 尚未实现。

## 目录

```text
AI_WORKSPACE/
├── _SYSTEM/                 系统宪法、协议和文件规则
├── CORE/
│   ├── index/               Filesystem Index 与 SQLite 持久化
│   ├── context/             Context Engine 边界
│   ├── gateway/             Context Gateway 边界
│   ├── protocol/            Agent 请求协议边界
│   └── common/              配置、启动入口等公共基础设施
├── PROJECTS/                项目目录和项目模板
├── DASHBOARD/               中央 Dashboard 和 Index 数据
├── LOGS/                    Append-only 日志
├── TASKS/                   Task 记录
├── config/                  系统配置
└── tests/                   自动化测试
```

## 技术栈

- Python 3.11+：核心运行时
- Python `unittest`：自动化测试，无第三方依赖
- SQLite：Filesystem Index 持久化，支持事务和外键
- Git：代码版本管理

当前阶段与后续范围见 [`PROJECT.md`](PROJECT.md)。核心原则和 Agent 边界见 [`_SYSTEM/CONSTITUTION.md`](_SYSTEM/CONSTITUTION.md) 与 [`_SYSTEM/AGENT_PROTOCOL.md`](_SYSTEM/AGENT_PROTOCOL.md)。
