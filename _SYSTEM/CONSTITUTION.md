# AI Workspace Constitution

## 系统目标

让计算机负责定位，让 LLM 负责认知。所有进入模型 Context 的本地信息都应经过确定性 Index、Context Gateway 和 Context Engine 的控制。

## 不可违反的边界

1. LLM / Agent 不得直接访问本地文件系统。
2. LLM / Agent 不得直接访问 SQLite 或遍历任意项目目录。
3. Index 必须能够在没有 LLM、Embedding 或向量数据库时独立运行。
4. Gateway 是 AI 与 Index 之间的唯一标准接口，并负责权限、项目隔离和预算。
5. Index 数据、Context 组装、Task、Git 和日志保持职责分离。

## Phase 0 范围

Phase 0 只建立工程骨架、配置入口、文档结构和测试框架。任何需要扫描文件、建立数据库、解析 AST 或访问 Git 的实现都属于后续阶段。

## 当前状态

Phase 0 到 Phase 10 的核心 MVP 已完成：Filesystem Index、Search、Python Symbol / Relation、Gateway、Context Engine、Adapter、Dashboard、Audit 和 Maintenance。多语言静态分析、完整 Git 历史、生产级 Dashboard 和 OS 级 Agent 沙箱仍是后续增强。

应用层 Gateway 只能控制遵守协议的调用者。若 Agent 被视为不可信代码，必须通过独立进程、独立 OS 用户、文件 ACL、容器或其他沙箱建立真正的能力边界；同一 Python 进程内的模块导出不能提供 OS 级安全保证。

