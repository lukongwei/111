# Decision Log

本文件按 append-only 原则维护。每条记录保留决定、原因、替代方案和不确定性。

## 2026-10-02 - Phase 0 采用 Python 标准库

- **决定**：使用 Python 3.11+ 和 `unittest`，不引入第三方运行时依赖。
- **原因**：Phase 0 只需要启动、配置读取和骨架验收；标准库已经提供 `tomllib` 和 `unittest`，能够降低安装和维护成本。
- **替代方案**：引入 pytest、配置框架或 Web 框架。
- **不确定性**：当 Phase 1 开始实现 Index 或服务接口时，是否需要引入第三方依赖，届时根据明确技术收益重新评估。

## 2026-10-02 - Phase 0 只建立边界

- **决定**：不在本阶段实现 SQLite、文件扫描、AST、Gateway 或 Context Engine。
- **原因**：工程规范要求每次只完成当前 Phase，避免提前固化未经验证的数据结构和访问协议。
- **替代方案**：先做一个端到端演示版本。
- **不确定性**：Phase 1 的 Index schema 和增量策略留到进入 Phase 1 时设计并测试。

## 2026-10-02 - Phase 1 文件身份与扫描策略

- **决定**：File ID 使用 SQLite 单调计数器分配；删除记录保留，不复用 ID；唯一 Hash 匹配且旧路径消失时识别移动。
- **原因**：路径不是身份；唯一内容匹配可确定性保留移动文件身份，歧义匹配则不能安全推断。
- **替代方案**：用路径或内容 Hash 直接生成 File ID，或通过相似度猜测移动。
- **不确定性**：移动同时修改内容无法仅由文件系统事实证明身份，当前按新增/删除处理；未来可评估 Git rename 信息。

## 2026-10-02 - Phase 1 索引数据库位置

- **决定**：SQLite 文件存放在 `DASHBOARD/data/index.sqlite3`，数据库 schema 版本为 1。
- **原因**：Index 数据由中央 Workspace 管理，不应分散到每个项目目录；版本标记避免静默使用不兼容 schema。
- **替代方案**：每个项目各自建立数据库。
- **不确定性**：大规模多项目场景的并发写入需求尚未出现，当前使用单一 SQLite 文件和事务。

## 2026-10-03 - 全链路 MVP 基线

- **决定**：连续实现 Search、Python Symbol / Relation、Gateway、Context、Adapter、Dashboard、Audit 和 Maintenance 的可运行标准库基线，并保持 Agent 只能经 Gateway 访问信息。
- **原因**：用户要求先连续推进全部步骤，最后统一验收；核心接口和测试需要形成完整链路才能验证架构边界。
- **替代方案**：继续逐 Phase 停下来等待确认，或引入 Web/ORM/向量数据库等第三方基础设施。
- **不确定性**：当前 Symbol、Relation、Dashboard 和维护规则是可解释 MVP，不替代多语言静态分析、完整 Git 历史和生产级前端。

## 2026-10-03 - Semantic Layer v0.1 作为语义事实层

- **决定**：在现有 Index SQLite 中增加 Problem、Goal、Module、Implementation、Semantic Relation、Annotation、History 和 Drift 表，并提供 `CORE.semantic.SemanticService`。
- **原因**：需要把数学问题、工程目标、模块和实现事实连接成可追溯图，同时区分 Human、AI、System 来源；语义模型明确要求这些约束先于优化和 Review 自动化。
- **替代方案**：把语义直接写入文件注释、复用普通 Index Relation，或立即实现 Goal 优化与自动冲突消解。
- **不确定性**：跨项目语义查询、Human 确认工作流、完整 Drift 检测、Review 和签名级来源证明留给后续阶段。

## 2026-10-04 - 开发历史整理与公开资料边界

- **决定**：新增 `DEVELOPMENT_HISTORY.md`，以仓库 Git 历史、项目文档和 Decision Log 为可验证来源，整理项目目标、架构思路、演进和实验设计；README 与 PROJECT 增加入口。
- **原因**：完整 ChatGPT 导出包含与项目无关的私人会话、账号数据和附件。筛查没有找到可确认为本项目开发过程的原始对话，因此不发布原始导出，也不将通用话题或未证实动机写成项目事实。
- **替代方案**：原样上传导出包或逐字公开聊天记录；这会暴露无关个人数据，也无法保证其适合作为项目开发史。
- **不确定性**：更早的构想和讨论若未记录在当前仓库或可确认的项目对话中，本文不会尝试补写；后续如发现经确认且可公开的资料，应以来源清晰的增补方式更新。

