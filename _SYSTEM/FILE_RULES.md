# File Rules

## 文件访问

- 原始项目文件保留在项目目录中，Index 只保存定位所需的元数据和结构信息。
- Agent 不得调用 `os.walk()`、`open()` 或等价接口绕过 Gateway 读取任意路径。
- 系统文件、密钥、凭据、Token、私钥和环境变量文件默认属于受保护范围。
- 所有项目必须使用 Git。

## 文件身份

文件身份 ID 与物理路径分离。移动且内容 Hash 唯一匹配的文件保留稳定 ID。Phase 1 已定义文件身份、元数据和索引状态 schema。

## 日志

Operation Log、Decision Log、Change Log 和 Token Audit 均采用 append-only 原则。Agent 不得静默改写历史记录。

