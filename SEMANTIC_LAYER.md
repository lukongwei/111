# Semantic Layer v0.1

本文档是 Workspace Semantic Layer 的实现约束摘要。完整形式语义以用户确认的《Semantic Layer 形式语义模型》为上位规范；实现可以改变存储和 API，但不能静默改变核心对象语义。

## 核心闭环

```text
Human -> Mathematical Problem -> Engineering Goal -> Module -> Implementation
```

实现反向保留可追溯关系：

```text
Implementation -> Module -> Goal -> Problem
```

当前对象类型：

- `problem`：Human 定义的 Mathematical Problem，ID 使用 `MP-` 前缀以区别 Project ID。
- `goal`：AI 组织的 Engineering Goal。
- `module`：实现一个或多个 Goal 的工程单元。
- `implementation`：System 观察到的文件、Symbol、运行实体或其他实现事实。

Semantic Layer 是图，不是树。Problem 与 Goal、Goal 与 Module、Module 与 Implementation 都允许多对多关系。

## 当前强制不变量

1. Problem 只能经当前受信任的管理调用创建，数据库触发器禁止直接 UPDATE/DELETE；`human="Human"` 是应用声明，不是身份认证。正式 Human 确认提案流程尚未实现，AI 修改请求会拒绝。
2. Module 必须持有有效 `primary_goal_id` 外键；创建时同时建立 `module -implements-> goal` 关系，不允许产生孤立的有效 Module。
3. 每个有效语义关系必须有非空 `rationale`，并记录 `Trigger / Gap / Response`。
4. `provenance` 必须区分 `Human`、`AI`、`System`；Implementation 的事实来源固定为 `System`。
5. Semantic history 只追加，不因修改、废弃或回滚删除旧版本。
6. 实现事实与语义判断分离；System 观察到的文件事实不能伪装成 AI 推断。
7. Drift 只生成 `review_required` 记录，不自动改写 Annotation 或 Problem。

## 代码入口

- [CORE/semantic/service.py](CORE/semantic/service.py)：Semantic Layer 持久化服务。
- [CORE/semantic/models.py](CORE/semantic/models.py)：Semantic 对象和关系模型。
- [CORE/index/database.py](CORE/index/database.py)：Semantic schema、历史和 Problem 保护。
- [tests/test_contracts.py](tests/test_contracts.py)：I1、I2、I5、I6 等契约测试。

## 当前明确不实现

以下内容属于 Review / Optimization 层，不是 v0.1 的自动行为：

- Module 必要性、冗余性和可替代性判断。
- Goal 最优性和自动排序。
- Goal 冲突自动消解。
- Module 自动合并或拆分。
- AI 自动修改 Mathematical Problem。
- 完整 Semantic Drift 自动判定。

AI 可以提出建议，但这些建议必须保留来源、理由和状态，不能伪装成 Human 已确认的语义。
