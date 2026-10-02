# CORE 模块职责

| 模块 | 当前职责 | 后续增强 |
| --- | --- | --- |
| `index` | 文件发现、SQLite、Search、Python Symbol、基础 Relation | 多语言 AST、完整 Git 分析 |
| `context` | 候选筛选、预算过滤和 Context Assembly | 更强相关性和关系扩展 |
| `gateway` | 请求校验、权限、项目隔离、Context Budget、敏感信息保护 | 多租户和更细粒度权限 |
| `protocol` | SEARCH、DESCRIBE、READ、RELATE、HISTORY、STATUS schema | 版本化网络协议 |
| `common` | 提供配置和启动入口 | 跨模块基础设施 |
| `adapter` | 模型无关的 Context 输入适配 | 各 LLM 厂商流式协议 |
| `audit` | Operation、Decision、Change、Token Audit 写入 | Dashboard 聚合和异常检测 |
| `maintenance` | 确定性健康检查 | 文档冲突和 Token 异常解释 |

依赖方向保持单向：`protocol` 定义数据，`gateway` 控制访问，`index` 定位信息，`context` 组装允许的信息。LLM 不直接依赖 `index` 或文件系统。

Filesystem Index API 和数据库说明见 [`index/README.md`](index/README.md)。

