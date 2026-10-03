# Security Boundary

## 当前实现能保证什么

在遵守 Gateway 协议的调用路径上，系统会执行：

- Project ID 校验和项目隔离。
- File / Symbol 所属项目校验。
- `.env`、credentials、password、secret、token、private key、API key 等敏感路径的保守拒绝。
- 删除或非 active 文件拒读。
- 索引 Hash 与读取时物理内容 Hash 一致性校验。
- 相对路径、路径穿越和符号链接读取拒绝。
- Gateway session 的持久化 Request / Read / File / Token Budget。
- Audit 表的 UPDATE / DELETE 数据库触发器保护。
- Dashboard 只允许回环地址启动。

## 当前实现不能单独保证什么

如果恶意 Agent 与 Gateway、Index 在同一个 Python 进程并拥有相同 OS 用户权限，那么恶意代码可以尝试：

```python
import sqlite3
from pathlib import Path
```

或者直接导入 `CORE.index`、打开项目文件、访问 SQLite 连接。这不是普通 Python 模块封装能够阻止的事情。

因此：

> Gateway 是应用层协议边界，不自动等于进程或操作系统安全边界。

## 不可信 Agent 的正确部署方式

不可信 Agent 应运行在单独的受控执行环境中：

```text
Agent Process / Sandbox
    - 无项目目录写权限
    - 无 Index SQLite 访问权限
    - 只拥有 Gateway IPC / HTTP 客户端权限
            |
            v
Gateway + Index Service Process
    - 受控项目目录权限
    - SQLite 权限
    - Budget / Permission / Audit
```

可选技术手段包括：

- 独立 OS 用户和文件 ACL。
- 独立进程和本地 IPC。
- Windows Job Object / AppContainer 或同等沙箱。
- 容器、虚拟机或受控执行器。
- 只把 Gateway 地址和短期 session credential 传给 Agent。

在完成上述部署前，项目只能宣称“协议遵守路径受控”，不能宣称“恶意 Agent 无法直接读取本地文件”。
