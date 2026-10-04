# Agent Instructions

本仓库遵循 `_SYSTEM/` 下的工程规范。当前基线是 Phase 0 到 Phase 10 的全链路 MVP；后续修改必须先读取 `PROJECT.md` 和 `REVIEW_PACKAGE.md`，并保持实现、测试和文档一致。

Agent 必须：

- 先读取相关规范和项目文档，再修改代码。
- 保持 Index、Gateway、Context、Task、Log 和 Git 的职责分离。
- 不允许让 LLM 或 Agent 直接读取任意本地路径。
- 每次阶段修改后运行全部测试，并如实报告失败。
- 更新相关文档、`PROJECT.md` 和重要设计决策。
- 对未实现的能力明确标记 TODO，不通过占位代码假装完成。
- 应用层 Gateway 不是 OS 沙箱；不可信 Agent 必须运行在独立进程、独立 OS 用户或受控沙箱中，不能与 Index 共享无限本地权限。
- Semantic Layer 的 Mathematical Problem 只能由 Human 明确确认；关系必须带 rationale 和 Trigger/Gap/Response，语义历史不得静默删除。
- 不得把 Semantic Layer 的 Annotation、Provenance 或 Drift 记录写成自动 Review、冲突裁决或最优性判断；未实现能力必须标记 TODO。

