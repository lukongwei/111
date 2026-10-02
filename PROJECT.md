# AI Workspace Project

## 项目目标

建立本地 AI Workspace，让多个 LLM / Agent 通过受控的 Context Gateway 共享确定性 Index 和最小充分 Context。

## 当前阶段

Phase 1：Filesystem Index。已实现显式项目注册、SQLite 持久化、目录和文件发现、元数据与 SHA-256、稳定 File ID、路径历史、唯一内容移动识别、删除 tombstone、增量更新和失败事务回滚。

尚未实现：Name / Path / Text / Metadata Search、AST / Symbol、Relation、Context Gateway、Context Engine、Agent Adapter、Dashboard 服务和 Audit 写入器。

## 验收标准

- Python 启动入口能够加载配置并输出当前阶段。
- `python -m unittest discover -s tests -v` 全部通过。
- 注册项目后，Index 能够增量更新 SQLite 记录。
- 索引只访问显式注册的项目；Agent 无直接访问权。

## 运行方式

```powershell
python -m CORE.common.app
python -m unittest discover -s tests -v
python -m CORE.index.cli --help
```

