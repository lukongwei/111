# File Rules

## 文件访问

- 原始项目文件保留在项目目录中，Index 只保存定位所需的元数据和结构信息。
- Agent 不得调用 `os.walk()`、`open()` 或等价接口绕过 Gateway 读取任意路径。
- 系统文件、密钥、凭据、Token、私钥和环境变量文件默认属于受保护范围。
- 所有项目必须使用 Git。

## 文件身份

文件身份 ID 与物理路径分离。移动文件不应改变其稳定 ID。文件身份、元数据、结构和状态的正式 schema 由 Phase 1 定义。

## 日志

Operation Log、Decision Log、Change Log 和 Token Audit 均采用 append-only 原则。Agent 不得静默改写历史记录。

