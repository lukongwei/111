# AI Workspace 开发过程与设计思路

> 本文面向项目使用者与贡献者，整理项目问题定义、架构选择和可验证的演进记录。它是根据仓库文档、Decision Log、Git 提交历史以及对用户提供的 ChatGPT 导出包进行筛查后编写的综合说明，不是原始对话逐字稿。

## 来源与边界

导出包是完整的个人 ChatGPT 数据导出，其中包含与项目无关的对话、账号信息和附件。筛查未找到能够确认为 AI Workspace 具体开发过程的原始讨论；匹配内容主要是通用 Agent / AI 工具话题和私人主题。因此，本文不引用或上传原始聊天、账号资料、附件或完整导出。项目演进的事实以仓库 Git 历史、Decision Log、项目规范和实现为准；不能由这些来源验证的早期动机不作推断。

## 要解决的问题

AI Workspace 的核心主张是：

> 让计算机负责定位，让 LLM 负责认知。

当多个 Agent 面对同一代码库时，如果每个 Agent 都自行遍历文件、重复搜索并自行决定读取范围，会产生重复工作、不可控的上下文规模和成本，也难以审计跨项目访问、敏感文件读取和内容来源。Workspace 把“找什么、能读什么、读多少”从模型自由发挥中拆出来，交由可测试的确定性程序处理，再将与任务相关的最小充分上下文交给模型。

项目目标不是让 Index 代替模型理解代码，也不是宣称已经构成操作系统安全沙箱。系统希望让模型专注于解释、推理和提出修改，同时让可重复验证的定位、预算、项目隔离和审计逻辑由普通程序负责。

## 架构原则

信息获取的目标路径是：

```text
Human Task
  -> Agent / Adapter
  -> Context Gateway
  -> Context Engine
  -> Deterministic Index
  -> Registered Project Files
```

各层边界如下：

| 组件 | 职责 | 不负责什么 |
|---|---|---|
| Index | 扫描登记项目，维护文件身份、元数据、文本、符号和代码关系；提供确定性搜索 | 不替模型作语义判断，不控制 Agent 的 OS 权限 |
| Gateway | 校验结构化请求、项目与对象归属、敏感路径、读取粒度和预算，并记录操作 | 不应成为任意路径文件读取 API；不是 OS 沙箱 |
| Context | 按任务检索候选、确定性排序、渐进读取并组装 Context Package | 不绕过 Gateway 直接打开项目文件 |
| Adapter | 将受控 Context 交给模型回调，隔离具体模型供应商 | 不直接访问 Index 或项目文件 |
| Task | 描述待完成工作和实验流程 | 不与索引事实或运行日志混为一体 |
| Log / Audit | 追加记录操作、决策、变更和成本等事实 | 不静默改写历史，不伪装成自动裁决 |
| Git | 版本化源码、规范和经审阅的公开文档 | 不存放本地运行数据库、凭据或未经审查的用户数据 |

Index 应能在没有 LLM、Embedding 或向量数据库时独立工作。语义关系用于表达工程概念时，必须包含 rationale 及 Trigger / Gap / Response；关系来源与注释是可追溯记录，不等于自动 Review、冲突裁决或最优性结论。Mathematical Problem 的定义权属于 Human，语义历史不得静默删除。

## 可验证的演进

以下时间线由仓库的 Git 提交与项目记录重建。提交时间只说明仓库中可验证的实现顺序，不代表更早的构想或全部设计讨论发生时间。

### Phase 0：先建立边界

2026-10-02 的 `10af1e1` 建立 Python 标准库项目骨架、配置入口、目录约定、测试框架和初始规范。Decision Log 记录了两个早期选择：先只建立工程边界，不提前实现数据库或文件扫描；优先使用 Python 标准库和 `unittest`，避免在需求尚不明确时增加运行时依赖。

### Phase 1：文件索引与稳定身份

提交 `79aee33` 增加 SQLite Index、项目注册、扫描、文件元数据、Hash 和增量更新。关键设计是路径不等于文件身份：File ID 单调分配且删除后不复用；只有内容 Hash 唯一匹配并且旧路径消失时，才将变化判定为移动。存在歧义时不猜测身份，以删除与新增处理并保留事实记录。

这一阶段为后续共享检索打基础：Index 管理可验证的文件事实，Agent 不需要各自维护一份目录认知。

### Phase 2：打通最小全链路

提交 `1225cc1` 将 Search、Python AST Symbol、基础 Relation、Gateway、Context、模型无关 Adapter、Dashboard JSON API、Audit 和 Maintenance 接入同一条可运行链路。实现覆盖从结构化请求到受预算的 Context Package，而不是只做孤立的扫描工具。

Relation 包括 imports、calls、tests 和 contains 的基础版本；它们是有限、确定性、可解释的工程索引，不宣称等价于完整静态类型分析或通用程序理解。

### 复查与安全边界加固

提交 `1820c14` 建立架构复查资料。随后 `faf859e` 根据边界审查加固跨项目对象校验、敏感路径过滤、删除状态处理、物理文件变化检查、预算持久化和审计写保护，并限制 Dashboard 仅监听回环地址、避免项目列表暴露绝对根路径。

这些措施改善的是遵守应用协议时的授权与审计能力，并不解决同一进程或同一 OS 用户内恶意代码直接访问磁盘的问题。因此不可信 Agent 必须在独立进程、独立 OS 用户、ACL、容器或其他受控沙箱中运行。这个限制是威胁模型的一部分，不应被 Gateway 的名称掩盖。

### Semantic Layer v0.1

提交 `7dfd728` 引入 Semantic Layer v0.1，把 Human-owned Problem、Engineering Goal、Module、System-observed Implementation、带理由的关系、Provenance、Annotation、History 和 Drift 记录纳入共享持久化模型。

设计上先记录语义事实及其来源，不急于自动优化或裁决。当前没有完整 Human 身份认证与 Problem 修改确认流程，也没有自动 Goal 冲突消解、最优性判断或完整 Drift 检测；这些能力仍需作为未完成事项说明。

### 开源维护准备

提交 `7dfd728`、`bd12b14` 和 `5cfe15c` 补充 CI、维护规则、公开项目介绍、贡献指南与 MIT 许可证。发布原则是只版本化经过审阅的源码、规范和可复现说明；SQLite 运行状态、凭据、Token、私人路径以及未脱敏实验材料留在本地。

## 当前实验问题

当前实验主线研究：

> 在控制其他变量的情况下，Workspace 是否降低 Agent 完成软件工程任务的成本？

实验分构建和维护两个阶段。比较时，两臂代码应逐字节相同，唯一实验变量是是否提供 Workspace；质量由独立探针评估，不依赖 Agent 自述。Workspace 臂若未同步或环境失配，该次结果作废；每个实验格至少重复三次后，才讨论分布。实验定义和结果应与个人路径、账号信息、原始会话及其他敏感数据分离。

这些是实验设计约束，不是实验结论。只有满足重复数和有效性要求后，才能基于观测数据回答 Workspace 是否降低成本。

## 当前实现状态与未完成项

项目当前是 Phase 0 到 Phase 10 核心骨架的全链路 MVP。公开仓库中有 Index、Search、Python Symbol / Relation、Gateway、Context、Adapter、Dashboard API、Audit、Maintenance、Semantic Layer v0.1 及其测试。

仍未完成或不能过度宣称的能力包括：多语言 AST 与完整静态分析、完整 Git History / rename、文档冲突检测、Token 异常检测、Dashboard 完整前端、多进程写入协调、通用数据库迁移、真实 Provider 集成、完整 Human 确认工作流，以及不可信 Agent 的 OS 级隔离部署。具体验收状态以 [`PROJECT.md`](PROJECT.md)、[`REVIEW_PACKAGE.md`](REVIEW_PACKAGE.md) 和 [`SECURITY_BOUNDARY.md`](SECURITY_BOUNDARY.md) 为准。

## 文档导航

- [`README.md`](README.md)：项目概览、安装运行和能力说明。
- [`PROJECT.md`](PROJECT.md)：当前目标、状态、限制和验收标准。
- [`REVIEW_PACKAGE.md`](REVIEW_PACKAGE.md)：架构、安全与测试复查入口。
- [`SECURITY_BOUNDARY.md`](SECURITY_BOUNDARY.md)：Gateway 与 OS / 进程隔离的边界。
- [`SEMANTIC_LAYER.md`](SEMANTIC_LAYER.md)：Semantic Layer v0.1 的数据与治理规则。
- [`LOGS/DECISION_LOG.md`](LOGS/DECISION_LOG.md)：按 append-only 维护的设计决策记录。
