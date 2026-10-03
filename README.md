# AI Workspace

AI Workspace 是本地 AI 信息基础设施：计算机负责定位，LLM 负责认知；Agent 只能通过 Context Gateway 获取受控 Context。

当前仓库已具备可运行的全链路 MVP 基线：Filesystem Index、确定性 Search、Python Symbol/Relation、Gateway、Context Engine、Agent Adapter、中央 Dashboard JSON API、Audit 和 Maintenance。

## 快速验证

要求 Python 3.11+，无第三方运行时依赖。

```powershell
python -m unittest discover -s tests -v
python -m CORE.common.app
python -m CORE.index.commands --help
python -m DASHBOARD.backend --help
```

## 本地工作流

SQLite 默认位于 `DASHBOARD/data/index.sqlite3`。项目必须显式注册；扫描器不跟随符号链接，并默认排除 `.git`、虚拟环境、缓存、依赖和构建目录。

```powershell
python -m CORE.index.commands register <项目名> <项目绝对路径>
python -m CORE.index.commands scan <项目ID>
python -m CORE.index.commands code <项目ID>
python -m CORE.index.commands search <项目ID> "关键词" --mode text
python -m CORE.index.commands request '{"op":"status","project_id":"P-000001"}'
python -m CORE.index.commands context <项目ID> "修改兴趣评分算法"
python -m CORE.index.commands health
python -m DASHBOARD.backend --port 8765
```

Dashboard API：

```text
GET /api/overview
GET /api/projects
GET /api/alerts
```

## 阶段状态

Phase 0 到 Phase 10 的核心 MVP 能力已建立，但部分能力仍是标准库基础版本。当前限制和后续增强见 [`PROJECT.md`](PROJECT.md).

需要人工或其他 GPT 复查时，直接使用 [`REVIEW_PACKAGE.md`](REVIEW_PACKAGE.md)。其中包含架构图、主要 API、验收结果、已知风险和可复制的审查提示词。

## 目录职责

```text
_SYSTEM/       系统规则与协议
CORE/index/    文件事实层、Search、Symbol、Relation
CORE/gateway/  唯一 Agent 访问入口
CORE/context/  渐进式 Context 组装
CORE/adapter/  模型无关 Agent Adapter
CORE/audit/    Append-only 审计
CORE/maintenance/ 健康检查
DASHBOARD/     中央 Dashboard API
PROJECTS/      项目模板和项目目录
LOGS/          决策与运行日志
TASKS/         Task 记录
tests/         自动化测试
```
