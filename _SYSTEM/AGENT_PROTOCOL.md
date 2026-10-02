# Agent Protocol

## 当前状态

Phase 0 只定义模块边界，不开放实际的文件读取协议。Agent Adapter 尚未实现。

## 未来标准操作

Gateway 计划支持以下结构化操作：

- `SEARCH`
- `DESCRIBE`
- `READ`
- `RELATE`
- `HISTORY`
- `STATUS`

这些操作必须由 Gateway 验证后交给 Index / Context Engine 处理。请求内容不等于访问权限，权限和 Context Budget 由程序执行。

## 渐进式 Context

默认流程是从项目摘要开始，逐步获取候选文件、Symbol、关系和必要代码。系统不允许因为 Agent 请求不明确而一次性读取整个项目。

