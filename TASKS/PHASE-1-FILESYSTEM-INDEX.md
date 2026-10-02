# Task: Phase 1 Filesystem Index

## 目标

建立不依赖 LLM 的确定性文件 Index，支持显式项目注册、稳定身份、基础元数据和增量扫描。

## 范围

- SQLite schema、schema 版本和事务。
- 项目注册、文件与目录发现、默认排除规则。
- File ID / Project ID 分配及删除 tombstone。
- SHA-256、文件元数据、路径历史和唯一移动识别。
- 扫描运行记录、warning 和失败回滚。
- 本地管理 CLI、API 文档和自动化测试。

## 验收

- [x] 注册项目并持久化项目身份。
- [x] 首次扫描建立文件、目录和 Hash 记录。
- [x] 无变化的重复扫描不重算文件 Hash。
- [x] 修改文件保留 File ID 并更新 Hash。
- [x] 删除保留 tombstone；同路径重新出现恢复原 ID。
- [x] 唯一 Hash 移动保留 ID 并记录路径历史。
- [x] 重复 Hash 不合并，歧义移动产生 warning。
- [x] 排除默认缓存目录并跳过符号链接。
- [x] 扫描失败不提交部分文件变更。
- [x] 全部测试通过并更新项目文档。

## 不在范围内

全文搜索、AST / Symbol、Relation、Context Gateway、Context Engine、Dashboard Web 服务和 Token Audit。

