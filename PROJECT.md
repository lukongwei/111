# AI Workspace Project

## 项目目标

建立一个本地 AI Workspace，让多个 LLM / Agent 通过受控的 Context Gateway 共享确定性 Index 和最小充分 Context。

## 当前阶段

Phase 0：工程骨架。当前已建立目录结构、配置入口、模块边界、项目模板、文档结构和自动化测试框架。

未实现且不得在本阶段宣称完成：文件发现、稳定文件 ID、SQLite Index、全文搜索、AST / Symbol、Relation、Context Gateway、Context Engine、Dashboard 服务和 Audit 写入器。

## 验收标准

- Python 启动入口能够加载配置并输出当前阶段。
- `python -m unittest discover -s tests -v` 全部通过。
- Git 具有 Phase 0 初始提交。
- 未经确认不进入 Phase 1。

## 运行方式

```powershell
python -m CORE.common.app
python -m unittest discover -s tests -v
```

