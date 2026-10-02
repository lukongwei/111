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

Phase 0 已完成。Phase 1 Filesystem Index 已实现项目注册、确定性文件发现、SQLite 元数据、稳定文件身份和增量更新。全文搜索、AST、Gateway 和 Context Engine 仍未实现；Agent 不得直接使用本地 Index API。

