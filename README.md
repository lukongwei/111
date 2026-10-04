# AI Workspace

[![CI](https://github.com/lukongwei/111/actions/workflows/ci.yml/badge.svg)](https://github.com/lukongwei/111/actions/workflows/ci.yml)

一个本地、可审计、受控的 AI Workspace 原型。

> **让计算机负责定位，让 LLM 负责认知。**

AI Workspace 的目标是让多个 LLM / Agent 共享同一份确定性项目 Index，并通过 Context Gateway 获取完成任务所需的最小充分 Context。Agent 不需要、也不应该反复遍历整个文件系统。

## 为什么做

直接把项目目录交给 Agent 会带来几个问题：

- 每个 Agent 都要重复搜索、读取和理解同一批文件。
- 上下文大小不可控，成本和结果质量难以比较。
- 跨项目读取、敏感文件泄露和任意路径访问很难审计。
- 文件移动、删除、代码关系和语义解释容易被混在一起，事实与推断无法区分。

这个项目把问题拆成几个职责清晰的层：Index 负责确定性定位，Gateway 负责访问控制，Context 负责组装最小上下文，Semantic Layer 负责记录工程意义和可追溯关系，Audit 负责留下不可静默修改的运行事实。

## 项目定位

本仓库是一个 **Phase 0 到 Phase 10 的全链路 MVP 和实验基线**，不是生产级 Agent 沙箱，也不是完整的代码理解引擎。

当前主线实验研究的问题是：

> 在控制其他变量的情况下，Workspace 是否能降低 Agent 完成软件工程任务的成本？

实验分为构建和维护两个阶段，要求对照臂代码逐字节一致、使用独立质量探针，并且每个实验格至少有 3 次重复后再讨论分布。

## 架构

```text
Human Task
    |
    v
Agent / LLM Adapter
    |
    | structured request
    v
Context Gateway
    |  project isolation
    |  sensitive-path protection
    |  read granularity and budget
    |  operation audit
    v
Context Engine
    |  deterministic candidate selection
    |  relation expansion
    |  progressive reads
    v
Deterministic Index
    |  filesystem metadata, hashes, symbols, relations, FTS5
    v
SQLite + registered project files
```

### 访问边界

Agent 获取项目内容的标准路径是：

```text
Agent -> Gateway -> Context -> Index -> registered project files
```

Gateway 会校验项目和对象归属、拒绝敏感路径、拒绝删除文件和路径穿越，并执行请求数、读取次数、文件数和 token 预算。Context Engine 不直接打开项目文件。

**重要：Gateway 是应用层协议边界，不是 OS 沙箱。** 如果 Agent 运行在同一个 Python 进程或同一个有项目目录权限的 OS 用户下，恶意代码仍可能绕过 Python API 直接访问文件或 SQLite。不可信 Agent 必须放在独立进程、独立 OS 用户、ACL、容器或其他受控沙箱中。完整边界说明见 [`SECURITY_BOUNDARY.md`](SECURITY_BOUNDARY.md)。

## 当前能力

- **Filesystem Index**：项目注册、SQLite 持久化、文件元数据、SHA-256、稳定 File ID、增量扫描、移动和删除历史。
- **Deterministic Search**：按文件名、路径、文本和元数据搜索；文本搜索使用 SQLite FTS5。
- **Python Code Index**：Python AST 的 Class、Function、Import，以及基础的 `imports`、`calls`、`tests`、`contains` 关系。
- **Context Gateway**：结构化请求、项目隔离、敏感文件保护、读取粒度、Context Budget 和操作审计。
- **Context Engine**：候选检索、确定性排序、关系扩展、渐进式读取和 Context Package。
- **Semantic Layer v0.1**：Human-owned Mathematical Problem、Engineering Goal、Module、System Implementation、带 rationale 与 Trigger/Gap/Response 的关系、Provenance、Annotation、History 和 Drift Review 记录。
- **Audit / Maintenance**：Operation、Decision、Change、Token Audit 的 append-only 写入，以及项目根目录、失败扫描和孤立 Symbol 等确定性检查。
- **Dashboard API**：基于标准库的本地 JSON HTTP API，读取共享 Index 的聚合视图，并提供 Console 操作入口。
- **Model-neutral Adapter**：核心系统不绑定 GPT、Claude、Qwen、DeepSeek 或其他具体模型提供商。

## 快速开始

要求 Python 3.11 或更高版本；运行时只使用 Python 标准库。

```powershell
# 运行全部测试
python -m unittest discover -s tests -v

# 启动检查和命令帮助
python -m CORE.common.app
python -m CORE.index.commands --help
python -m DASHBOARD.backend --help
```

### 注册并索引一个项目

```powershell
python -m CORE.index.commands register <项目名> <项目绝对路径>
python -m CORE.index.commands scan <项目ID>
python -m CORE.index.commands code <项目ID>
```

示例搜索和 Context 组装：

```powershell
python -m CORE.index.commands search <项目ID> "interest score" --mode text
python -m CORE.index.commands search <项目ID> "scorer" --mode name
python -m CORE.index.commands context <项目ID> "修改兴趣评分算法"
python -m CORE.index.commands health
```

默认 SQLite 路径是 `DASHBOARD/data/index.sqlite3`。它是本地运行状态，连同 WAL、SHM 和 journal sidecar 一起被 `.gitignore` 排除，不应提交到 Git。

### 启动 Dashboard

```powershell
python -m DASHBOARD.backend --port 8765
```

然后访问 <http://127.0.0.1:8765/>。当前 Dashboard 主要是 JSON API；`DASHBOARD/frontend/` 仍是前端预留目录。

## API 概览

### Gateway 操作

Gateway 支持以下结构化操作：

```text
search    搜索文件身份和元数据，不直接返回全文
describe  描述文件或 Symbol
read      在预算和安全规则内读取文件或 Symbol
relate    查询代码关系
history   查询文件路径历史
status    查询项目索引状态
```

请求示例：

```json
{
  "op": "search",
  "project_id": "P-000001",
  "agent": "review-agent",
  "task": "修改兴趣评分算法",
  "query": "interest score",
  "mode": "text",
  "limit": 10
}
```

### Dashboard API

```text
GET  /api/overview
GET  /api/projects
GET  /api/alerts

GET  /api/console/projects
GET  /api/console/projects/{project_id}/search?query=...&mode=text&limit=10
GET  /api/console/projects/{project_id}/objects/{object_id}
GET  /api/console/projects/{project_id}/status
POST /api/console/projects
POST /api/console/projects/{project_id}/scan
POST /api/console/projects/{project_id}/code
POST /api/console/projects/{project_id}/context
```

Dashboard 默认只绑定回环地址。当前 API 没有认证，不能把它当作同机进程之间的安全授权边界。

## Semantic Layer

Semantic Layer v0.1 记录以下可追溯链条：

```text
Human Mathematical Problem
        -> Engineering Goal
        -> Module
        -> System-observed Implementation
```

它的关键约束是：

- Mathematical Problem 只能由 Human 明确定义；当前没有完整的 Human 身份认证和确认提案流程。
- 每条语义关系必须带 `rationale` 以及 `Trigger / Gap / Response`。
- `Provenance` 区分 `Human`、`AI` 和 `System`。
- Semantic history 和关系记录 append-only，不能静默删除。
- Drift 只产生 `review_required` 事实，不自动裁决冲突、最优性或 Problem 修改。

实现入口见 [`CORE/semantic/service.py`](CORE/semantic/service.py)，约束摘要见 [`SEMANTIC_LAYER.md`](SEMANTIC_LAYER.md)。

## 目录导航

```text
_SYSTEM/          宪法、协议、文件规则和文档规则
CORE/index/       文件事实层、Search、Python Symbol、Relation
CORE/gateway/     Agent 的唯一标准访问入口
CORE/context/     确定性 Context 组装
CORE/protocol/    结构化 Request / Response 模型
CORE/adapter/     模型无关的 Agent Adapter
CORE/semantic/    Semantic Layer v0.1 持久化服务
CORE/audit/       Operation、Decision、Change、Token Audit
CORE/maintenance/ 确定性健康检查
DASHBOARD/        本地 JSON HTTP API 和共享数据目录
PROJECTS/         项目夹具和模板
TASKS/            阶段任务、行为规则和实验提示词
LOGS/             决策记录和经过审阅的实验资料
tests/            自动化测试
```

## 文档入口

- [`PROJECT.md`](PROJECT.md)：当前目标、状态、限制和验收标准。
- [`REVIEW_PACKAGE.md`](REVIEW_PACKAGE.md)：架构、安全和代码复查资料。
- [`SECURITY_BOUNDARY.md`](SECURITY_BOUNDARY.md)：Gateway 与 OS / 进程沙箱的边界。
- [`SEMANTIC_LAYER.md`](SEMANTIC_LAYER.md)：Semantic Layer v0.1 约束。
- [`MAINTENANCE.md`](MAINTENANCE.md)：本地检查、发布和运行状态维护规则。
- [`CONTRIBUTING.md`](CONTRIBUTING.md)：贡献流程和提交前要求。
- [`_SYSTEM/`](_SYSTEM/)：仓库级不可违反规范。

## 当前限制与后续方向

以下能力仍未完成，不能按生产能力宣称：

- 只有 Python 具备 AST Symbol 和基础 Relation，其他语言目前主要是文件级 Index。
- `calls` 等 Relation 是确定性启发式分析，不等价于完整静态类型分析。
- Dashboard 目前是标准库 JSON API，没有完整前端 UI。
- Git History、复杂 Git rename、文档过期检测、Token 异常检测和多进程写入协调仍是增强项。
- Index schema v4 只对部分旧版本做结构补齐和版本提升，没有通用迁移工具。
- Semantic Layer 还没有自动 Review、Goal 冲突消解、必要性/最优性判断、完整 Drift 检测和 Human 确认工作流。
- 真正不可信 Agent 的 OS 级隔离需要独立部署，不能只靠 Python Gateway 封装解决。

## 测试与维护

本地提交前运行：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q CORE DASHBOARD tests
git diff --check
```

GitHub Actions 会在 Python 3.11、3.12 和 3.13 上运行这些检查。提交前请确认没有 `.env`、凭据、Token、私钥、用户数据或未经脱敏的实验日志。详细流程见 [`CONTRIBUTING.md`](CONTRIBUTING.md) 和 [`MAINTENANCE.md`](MAINTENANCE.md)。

## 许可证

本项目采用 [MIT License](LICENSE)。使用、修改或再分发时，请保留版权与许可声明。该许可不提供任何明示或默示的担保。
