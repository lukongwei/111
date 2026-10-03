# AI Workspace 项目复查包

> 用途：这份文档用于人工复查，也可以整体复制给其他 GPT 做架构、代码和安全审查。
>
> 复查基线：`1225cc1 feat: complete full-chain workspace mvp`
>
> 复查日期：2026-10-03（Asia/Shanghai）

## 0. 先看结论

这是一个本地 AI Workspace 的全链路 MVP，不是生产级完成品。

核心目标：

```text
让计算机负责定位，让 LLM 负责认知。
```

核心访问边界：

```text
Agent / LLM
    |
    v
Context Gateway
    |
    v
Context Engine
    |
    v
Index Service
    |
    v
SQLite + Project Filesystem
```

设计要求是：Agent 不得直接遍历文件系统、读取任意绝对路径或直接访问 SQLite。

当前已经实现：

- Filesystem Index
- SQLite 持久化
- 稳定 Project ID / File ID
- 增量扫描、Hash、删除历史、移动识别
- Name / Path / Text / Metadata Search
- Python AST Symbol Index
- 基础 `imports` / `calls` / `tests` / `contains` Relation
- Context Gateway
- 项目隔离、敏感路径保护、读取粒度、Context Budget
- Context Engine
- 模型无关 Agent Adapter
- Dashboard JSON HTTP API
- Operation / Decision / Change / Token Audit
- Maintenance 健康检查

当前不能宣称为生产级的部分：

- 只对 Python 做 AST Symbol / Relation。
- Relation 是基础确定性分析，不是完整静态类型分析。
- Dashboard 目前主要是 JSON API，没有完整前端 UI。
- Git History、复杂 Git rename、文档冲突检查、Token 异常检测和多进程并发写入仍未完成。

## 1. 重要规范冲突

根目录 [`AGENTS.md`](AGENTS.md) 目前仍写着：

```text
当前只执行 Phase 0，任何进入 Phase 1 的实现都需要用户明确确认。
```

但之后用户已经明确授权连续推进全部步骤，当前代码和 [`PROJECT.md`](PROJECT.md) 已进入全链路 MVP。

因此复查时请采用以下解释：

1. `AGENTS.md` 是过期的阶段限制，不能代表当前实现状态。
2. 当前有效的实现基线是 Git 提交 `1225cc1`。
3. 如果要继续开发，应该先决定是更新 `AGENTS.md`，还是恢复“只执行 Phase 0”的约束。
4. 在这项冲突解决前，不应让自动化 Agent 根据 `AGENTS.md` 擅自判断项目仍处于 Phase 0。

这项规范漂移本身就是本项目的 P1 复查问题。

## 2. 项目目录

```text
AI_WORKSPACE/
├── _SYSTEM/
│   ├── CONSTITUTION.md       系统不可违反的边界
│   ├── AGENT_PROTOCOL.md     Agent / Gateway 协议说明
│   ├── FILE_RULES.md         文件访问、身份和日志规则
│   └── DOCUMENTATION_RULES.md 文档维护规则
├── CORE/
│   ├── index/                文件事实层、搜索、Symbol、Relation
│   ├── gateway/              Agent 唯一访问入口
│   ├── context/              Context 组装
│   ├── protocol/             结构化 Request / Response 模型
│   ├── adapter/              模型无关 Agent Adapter
│   ├── audit/                Append-only 审计写入器
│   ├── maintenance/          确定性健康检查
│   └── common/               配置和启动入口
├── PROJECTS/                 项目目录和项目模板
├── DASHBOARD/
│   ├── backend/              Dashboard JSON HTTP API
│   ├── frontend/             前端预留
│   └── data/                 中央 SQLite 数据库位置
├── LOGS/                     决策和日志说明
├── TASKS/                    Task 记录
├── tests/                    自动化测试
├── config/system.toml        系统配置
├── PROJECT.md                当前项目状态
└── REVIEW_PACKAGE.md         本复查包
```

## 3. 架构图

### 3.1 运行时架构

```text
                         用户任务
                            |
                            v
                    Agent / LLM Adapter
                            |
                            | Structured Request
                            v
                  +-----------------------+
                  |   Context Gateway    |
                  |-----------------------|
                  | Request Validation    |
                  | Project Isolation     |
                  | Sensitive Protection |
                  | Context Budget        |
                  | Operation Audit       |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  |    Context Engine    |
                  |-----------------------|
                  | Candidate Search      |
                  | Deterministic Ranking |
                  | Relation Expansion    |
                  | Progressive Read      |
                  | Context Assembly      |
                  +-----------+-----------+
                              |
                              v
                  +-----------------------+
                  |     Index Service     |
                  |-----------------------|
                  | Filesystem Scanner    |
                  | SQLite                 |
                  | FTS5 Search            |
                  | Python AST            |
                  | Symbol / Relation     |
                  | Metadata / Hash       |
                  +-----------+-----------+
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
        SQLite Index                    Registered Projects
```

### 3.2 信息获取流程

```text
用户：修改兴趣评分算法
        |
        v
Agent Adapter
        |
        v
Gateway SEARCH
        |
        v
Index: FTS5 找候选文件
        |
        v
Context Engine: 排序 + 关系扩展
        |
        v
Gateway READ Symbol / File
        |
        v
预算过滤后的 Context Package
        |
        v
LLM 生成修改建议或代码变更
```

### 3.3 代码依赖方向

```text
protocol  -> 定义结构化数据
index     -> 只负责事实定位和确定性索引
gateway   -> 控制外部访问，不让 Agent 直接碰 Index
context   -> 通过 Gateway 组装 Context
adapter   -> 将 Context Package 交给任意模型回调
dashboard -> 只读共享数据库聚合视图
audit     -> 追加审计事实
maintenance -> 读取系统事实做健康检查
```

复查重点：`context` 不应该绕过 `gateway` 直接读取文件；`adapter` 不应该绕过 `gateway` 直接访问 Index；Dashboard 不应该建立项目自己的第二套数据存储。

## 4. 模块职责与主要文件

### Index

主要文件：

- [`CORE/index/database.py`](CORE/index/database.py)：SQLite schema、schema version、事务。
- [`CORE/index/service.py`](CORE/index/service.py)：项目注册、扫描、文件查询、Search/Code 查询入口。
- [`CORE/index/search.py`](CORE/index/search.py)：Name、Path、Text、Metadata Search。
- [`CORE/index/symbols.py`](CORE/index/symbols.py)：Python AST Symbol。
- [`CORE/index/relations.py`](CORE/index/relations.py)：基础关系。
- [`CORE/index/metadata.py`](CORE/index/metadata.py)：Hash、大小、时间和语言识别。
- [`CORE/index/exclusions.py`](CORE/index/exclusions.py)：默认排除规则。

核心持久化表：

```text
projects
files
file_paths
directories
index_runs
scan_warnings
file_text_fts
symbols
relations
```

文件身份规则：

```text
路径变化 != 文件身份变化
```

`File ID` 使用 SQLite 单调计数器分配。内容 Hash 唯一匹配时可识别移动；无法证明的移动按删除 + 新增处理，并记录 warning。

### Gateway

主要文件：

- [`CORE/gateway/service.py`](CORE/gateway/service.py)
- [`CORE/protocol/models.py`](CORE/protocol/models.py)

支持操作：

```text
search
describe
read
relate
history
status
```

预算字段：

```text
max_total_tokens
max_files
max_read_operations
max_single_file_tokens
max_request_count
```

### Context Engine

主要文件：

- [`CORE/context/engine.py`](CORE/context/engine.py)

流程：

```text
Task
  -> SEARCH
  -> 确定性排序
  -> RELATE 扩展
  -> READ
  -> ContextPackage
```

Context Engine 不应该直接调用 `open()`、`os.walk()` 或 `Path.read_text()` 读取项目文件。

### Adapter

主要文件：

- [`CORE/adapter/service.py`](CORE/adapter/service.py)

当前 Adapter 接收一个模型回调：

```python
AgentAdapter.run(request, model_callback)
```

核心系统不绑定 GPT、Claude、Qwen、DeepSeek 等具体模型。

### Dashboard

主要文件：

- [`DASHBOARD/backend/server.py`](DASHBOARD/backend/server.py)
- [`DASHBOARD/backend/service.py`](DASHBOARD/backend/service.py)

当前 API：

```text
GET /api/overview
GET /api/projects
GET /api/alerts
```

Dashboard 只读共享 SQLite 聚合结果，不是另一个项目数据库。

### Audit

主要文件：

- [`CORE/audit/service.py`](CORE/audit/service.py)

写入类型：

```text
operation_log
decision_log
change_log
token_audit
```

当前 API 只提供追加写入，不提供静默修改历史的接口。

## 5. 主要 API 示例

### 注册和扫描

```powershell
python -m CORE.index.commands register demo C:\path\to\demo
python -m CORE.index.commands scan P-000001
python -m CORE.index.commands code P-000001
```

### 搜索

```powershell
python -m CORE.index.commands search P-000001 "interest score" --mode text
python -m CORE.index.commands search P-000001 "scorer" --mode name
python -m CORE.index.commands search P-000001 "src/" --mode path
python -m CORE.index.commands search P-000001 "python" --mode metadata
```

### Gateway Request

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

细粒度读取：

```json
{
  "op": "read",
  "project_id": "P-000001",
  "agent": "review-agent",
  "id": "S-xxxxxxxxxxxx"
}
```

### Context

```powershell
python -m CORE.index.commands context P-000001 "修改兴趣评分算法"
```

### Dashboard

```powershell
python -m DASHBOARD.backend --port 8765
```

## 6. 测试与验收

执行：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q CORE DASHBOARD tests
git diff --check
```

当前基线结果：

```text
25 tests passed
1 symbolic-link test skipped
```

测试文件：

- [`tests/test_index.py`](tests/test_index.py)：文件发现、ID、增量、删除、移动、Hash、事务回滚。
- [`tests/test_platform.py`](tests/test_platform.py)：Search、Symbol、Relation、Gateway、Context、Adapter、Dashboard、Audit、Maintenance。
- [`tests/test_contracts.py`](tests/test_contracts.py)：协议校验、schema version。
- [`tests/test_workspace.py`](tests/test_workspace.py)：配置和目录边界。

注意：符号链接测试在当前 Windows 环境因权限限制跳过，不代表符号链接行为被完整验证。

## 7. 复查重点

### P0：必须确认的架构边界

1. LLM / Agent 是否存在绕过 Gateway 的本地文件读取路径？
2. `ContextEngine` 是否只通过 Gateway 获取内容？
3. 是否存在任意绝对路径可以从 Request 进入文件读取？
4. `project_id` 是否在每一个对象读取和关系查询中被验证？
5. Budget 是否由程序强制执行，而不是只在 Prompt 中描述？
6. 敏感文件规则是否覆盖 `.env`、credentials、password、token、API key、private key 等变体？
7. 失败扫描是否会留下半成品 Index？
8. Audit 是否真的 append-only？

### P1：当前实现中建议重点审查的风险

1. [`AGENTS.md`](AGENTS.md) 与当前实际阶段冲突，可能导致后续 Agent 做出错误决策。
2. 敏感路径判断目前是规则集合匹配，应该重点验证 `credentials.json`、`api_key.txt`、`private.pem`、嵌套路径和大小写变体。
3. SQLite schema 从版本 1 到版本 2 当前没有迁移工具；旧数据库可能需要重建。
4. FTS5 依赖当前 Python SQLite 编译选项，跨环境部署需要检查 FTS5 可用性。
5. Relation 的 `calls` 是基础启发式分析，不能当作完整调用图。
6. `called_by` / `tested_by` 等反向关系需要确认是查询时反向推导，还是数据库中显式维护。
7. Context Engine 的关系扩展、读取次数和 `max_files` 计数需要检查是否符合预算语义。
8. 单 SQLite 文件、多线程 Dashboard 和并发扫描的写入策略需要压测。
9. Dashboard 当前没有认证和远程暴露防护，应该只绑定本地地址。
10. Index 读取原始文件使用 UTF-8 replacement，二进制和超大文件策略需要明确。

### P2：后续质量提升

1. 增加多语言 AST 插件接口。
2. 增加 Git History、rename 和 changed-by 查询。
3. 增加真正的 Token 计数器，而不是字符估算。
4. 增加数据库迁移框架。
5. 增加 Dashboard 前端和可视化关系图。
6. 增加并发扫描、锁、崩溃恢复和长期运行测试。
7. 接入真实 Agent Provider 时，确保 Provider 只收到 Context Package，不收到项目根路径或 SQLite 路径。

## 8. 复查输出格式

请审查者按以下顺序输出：

```text
1. Findings：按 P0 / P1 / P2 排序，必须给出文件和行号。
2. Security：是否存在绕过 Gateway、路径穿越、跨项目读取、敏感信息泄露。
3. Correctness：Index、Search、Symbol、Relation、Context 的逻辑错误。
4. Data integrity：事务、稳定 ID、删除/移动、schema migration。
5. Tests：缺失的测试和当前测试的误报风险。
6. Architecture：是否符合 Index / Gateway / Context / Adapter 分层。
7. Recommended next steps：只列最重要的 3 到 8 项。
8. Final verdict：Approved / Approved with conditions / Needs changes。
```

不要只总结功能；优先寻找会导致错误读取、越权读取、数据损坏或 Context 失控的问题。

## 9. 可直接粘给 GPT 的复查提示词

```text
你现在是一个严格的资深架构、安全和代码审查员。

请审查我提供的 AI Workspace 项目。项目目标是：让计算机负责定位，让 LLM 负责认知；LLM / Agent 不得直接读取本地文件系统或 SQLite，所有信息必须经过 Context Gateway、Index 和 Context Engine。

请重点审查：

1. Agent / LLM 是否可能绕过 Gateway 直接读文件、遍历目录或访问 SQLite。
2. Gateway 是否正确执行项目隔离、敏感路径保护、READ 粒度和 Context Budget。
3. 是否存在路径穿越、绝对路径注入、符号链接绕过、大小写绕过或敏感文件名变体绕过。
4. Index 的稳定 File ID、移动识别、删除 tombstone、重复 Hash、增量更新和 SQLite 事务是否正确。
5. schema version 是否可升级，旧数据库是否会被破坏或静默误用。
6. FTS5 Search、Python AST Symbol、Relation 和 Context Engine 是否有逻辑错误。
7. Context Engine 是否真的只通过 Gateway 获取内容，是否可能超出预算或读取无关文件。
8. Dashboard、Audit、Maintenance 是否违反职责分离，是否有日志篡改或敏感数据泄漏问题。
9. 测试是否覆盖真正的失败路径，是否存在只测 happy path 的假安全感。
10. 当前文档、AGENTS 规则和代码状态是否一致。

审查时请遵守：

- Findings 优先于总结。
- 按严重性排序：P0、P1、P2、P3。
- 每个 Finding 必须包含：严重性、文件、行号、问题、影响、修复建议。
- 没有问题时也要说明剩余测试缺口和残余风险。
- 不要因为测试通过就默认架构正确。
- 不要提出与当前目标无关的大规模重构。

项目复查基线：
- Git commit: 1225cc1
- Python: 3.11+
- Runtime dependencies: Python standard library
- Test command: python -m unittest discover -s tests -v
- Expected baseline: 25 passed, 1 symbolic-link test skipped on restricted Windows environments

请最后给出：
1. Findings
2. Security verdict
3. Architecture verdict
4. Test gap list
5. Top 5 recommended fixes
6. Final verdict: Approved / Approved with conditions / Needs changes
```

