# AI Workspace Project

## 项目目标

建立本地 AI Workspace，让多个 LLM / Agent 通过受控的 Context Gateway 共享确定性 Index 和最小充分 Context。

## 当前状态

已完成一个可运行的全链路 MVP 基线，覆盖规范中的 Phase 0 到 Phase 10 核心骨架：

- Filesystem Index：项目注册、SQLite、文件元数据、Hash、稳定 ID、增量扫描、移动/删除历史。
- Search：Name、Path、Text、Metadata 四种确定性搜索。
- Symbol：Python AST 的 Class、Function、Import 基础结构。
- Relation：imports、calls、tests、contains 基础关系。
- Gateway：结构化请求、项目隔离、敏感文件保护、读取粒度、Context Budget 和操作审计。
- Context：确定性候选检索、渐进式读取和 Context Package。
- Adapter：模型无关的 Agent 输入/输出适配器。
- Dashboard：中央 JSON HTTP API 和聚合读模型。
- Audit：Operation、Decision、Change、Token Audit append-only 写入器。
- Maintenance：项目根目录、失败扫描、孤立 Symbol 等确定性健康检查。

## 当前明确限制

- 目前只对 Python 提供 AST Symbol 和基础 Relation；其他语言仍只有文件级 Index。
- 调用关系是确定性启发式的基础版本，不等价于完整静态类型分析。
- Dashboard 当前是标准库 JSON HTTP API，没有完整前端 UI。
- Git History、复杂 Git rename、文档过期检测、Token 异常检测和多进程写入协调仍属于增强项。
- Index schema 已升级到版本 2；旧版本数据库需要重新建立或显式迁移，当前不会静默兼容。

## 验收标准

- `python -m unittest discover -s tests -v` 全部通过。
- Index、Search、Symbol、Relation、Gateway、Context、Adapter、Dashboard、Audit、Maintenance 均有自动化覆盖。
- Agent 只能通过 Gateway 获取项目上下文，不能直接使用本地文件系统或 SQLite。
- 超过预算、跨项目、敏感路径和非法请求必须被拒绝并记录审计。
- 工作区保持 Git 可追踪且文档与实现一致。

## 运行方式

```powershell
python -m unittest discover -s tests -v
python -m CORE.common.app
python -m CORE.index.commands --help
python -m DASHBOARD.backend --help
python -m DASHBOARD.backend --port 8765
```

