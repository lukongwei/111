# Filesystem Index

Phase 1 的 Filesystem Index 是 MVP 的事实层；其上已接入确定性 Search、Python Symbol 和基础 Relation。所有能力不依赖 LLM。

## API

```python
from CORE.index import IndexDatabase, IndexService

with IndexDatabase("DASHBOARD/data/index.sqlite3") as database:
    index = IndexService(database)
    project = index.register_project("my-project", "/absolute/path/to/project")
    result = index.scan_project(project.project_id)
    files = index.list_files(project.project_id)
```

- `register_project(name, root_path)`：显式注册现存目录；同一规范化根路径重复注册返回原项目。
- `scan_project(project_id)`：扫描已注册根目录并事务化更新 Index；不完整扫描失败时不提交文件状态。
- `list_files(project_id, include_deleted=False)`：列出文件元数据，不返回文件内容。
- `get_file(file_id)`：按稳定 File ID 查询当前或删除状态记录。
- `list_file_paths(file_id)`：查询当前和历史相对路径。
- `list_directories(project_id)`：查询目录树。
- `list_warnings(run_id)`：查询符号链接跳过和歧义移动等扫描告警。

## File ID 与变更规则

- `P-000001`、`F-000001`、`D-000001` 分别由 SQLite 单调计数器分配，不依赖路径或 Hash。
- ID 不复用。删除保留为 tombstone；相同路径后续重新出现时恢复原 File ID。
- 路径以项目根为界，写入 POSIX 风格相对路径。
- 同路径文件只有大小、`mtime_ns`、`ctime_ns` 均未变化时才跳过 Hash 读取；元数据变化时重新计算 SHA-256。
- Hash 相同且旧路径消失、新路径唯一时，识别为移动并保留 File ID。
- 重复 Hash 或移动同时改内容无法确定身份时，不猜测；记录 warning，按删除/新增处理。
- 自然语言 Text Search 会将输入拆成安全的 AND 词项，避免 FTS5 操作符或标点改变查询语义。

## 扫描范围

默认排除 `.git`、`__pycache__`、虚拟环境、`node_modules`、构建目录和测试/类型检查缓存。符号链接不跟随，并产生 warning。不可完整读取目录或文件元数据时，本次扫描失败，不将部分文件差异写入 Index。

## SQLite

数据库路径由 `config/system.toml` 配置，默认是 `DASHBOARD/data/index.sqlite3`。Schema 版本存放在 `metadata` 表中。文件更新和目录树替换在同一事务中提交；每次扫描另有 `index_runs` 记录，失败状态和错误原因保留用于审计。

当前数据库 API 是本地管理接口，不是 Agent 权限边界。Agent 必须通过 `CORE.gateway.ContextGateway` 访问信息，不能直接调用 Index API。

