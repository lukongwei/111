# Agent Instructions

本仓库遵循 `_SYSTEM/` 下的工程规范。当前只执行 Phase 0，任何进入 Phase 1 的实现都需要用户明确确认。

Agent 必须：

- 先读取相关规范和项目文档，再修改代码。
- 保持 Index、Gateway、Context、Task、Log 和 Git 的职责分离。
- 不允许让 LLM 或 Agent 直接读取任意本地路径。
- 每次阶段修改后运行全部测试，并如实报告失败。
- 更新相关文档、`PROJECT.md` 和重要设计决策。
- 对未实现的能力明确标记 TODO，不通过占位代码假装完成。

