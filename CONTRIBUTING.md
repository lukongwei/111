# Contributing to AI Workspace

感谢关注这个实验性 Workspace。贡献的重点是保持事实、访问控制、语义和实验结果之间的边界清楚。

## 开始之前

先阅读：

1. [`AGENTS.md`](AGENTS.md)
2. [`PROJECT.md`](PROJECT.md)
3. [`REVIEW_PACKAGE.md`](REVIEW_PACKAGE.md)
4. [`_SYSTEM/`](_SYSTEM/)
5. [`SECURITY_BOUNDARY.md`](SECURITY_BOUNDARY.md)

源码修改前，应先理解对应模块的职责和已有测试。不要把未实现能力写成已完成，也不要用占位代码掩盖缺口。

## 工程边界

- Index 只负责确定性事实和定位。
- Gateway 是 Agent 获取项目 Context 的标准入口。
- Context Engine 通过 Gateway 获取内容，不直接遍历或读取项目文件。
- Task、Log、Git 和 Semantic Layer 不与 Index 混成一个职责。
- Semantic Mathematical Problem 只能由 Human 明确认定；关系必须带 rationale 和 Trigger/Gap/Response。
- Semantic history 不得静默删除。
- Gateway 不是 OS 沙箱；不可信 Agent 必须使用独立进程、OS 用户、ACL 或受控沙箱。

## 本地验证

```powershell
python -m unittest discover -s tests -v
python -m compileall -q CORE DASHBOARD tests
git diff --check
```

每次阶段性修改都应运行完整测试，并如实记录失败。新增行为要同时更新测试和相关文档。

## 提交建议

- 使用功能分支，例如 `codex/<short-description>`。
- 一个提交尽量只表达一个可理解的变更。
- 不提交 `DASHBOARD/data/` 下的 SQLite 运行数据库或 sidecar。
- 不提交 `.env`、凭据、Token、私钥、用户数据或未经脱敏的实验轨迹。
- 不修改或删除既有语义历史来“整理”结果。
- Pull request 描述中说明变更、测试命令、已知限制和是否涉及安全边界。

## Pull request 检查

提交前确认：

- [ ] 全量测试通过，或失败原因已明确说明。
- [ ] `compileall` 和 `git diff --check` 通过。
- [ ] 实现、测试和文档一致。
- [ ] 新增能力没有绕过 Gateway 或破坏模块职责分离。
- [ ] 敏感信息、SQLite 运行状态和本地绝对路径没有进入提交。
- [ ] 未实现能力标记为 TODO 或明确限制。

GitHub Actions 会在 Python 3.11、3.12 和 3.13 上执行基础 CI。CI 通过不等于完成 OS 级沙箱、安全审计或实验验收；这些边界仍需按项目文档单独判断。
