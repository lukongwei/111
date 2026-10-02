# CORE 模块职责

| 模块 | Phase 0 职责 | 后续职责 |
| --- | --- | --- |
| `index` | 保留模块边界 | 确定性文件发现、元数据、SQLite、FTS、AST、Symbol、Relation、Git |
| `context` | 保留模块边界 | 候选筛选、关系扩展、预算过滤和 Context Assembly |
| `gateway` | 保留唯一入口边界 | 请求校验、权限、项目隔离、Context Budget 和敏感信息保护 |
| `protocol` | 保留协议边界 | SEARCH、DESCRIBE、READ、RELATE、HISTORY、STATUS schema |
| `common` | 提供配置和启动入口 | 跨模块基础设施 |

依赖方向保持单向：`protocol` 定义数据，`gateway` 控制访问，`index` 定位信息，`context` 组装允许的信息。LLM 不直接依赖 `index` 或文件系统。

