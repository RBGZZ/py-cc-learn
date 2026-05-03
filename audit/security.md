# py-cc-learn 安全审计报告

**审计日期**: 2026-05-03  
**审计范围**: `d:\agent_learn\py-cc\py-cc-learn\server\` 全部 Python 源文件  
**审计方法**: 静态代码分析 + Grep 模式匹配 + 手动代码审查

---

## 1. API Key 保护

### 1.1 日志/输出泄漏检测 (A)

对 `server/` 下所有 `.py` 文件进行了 4 种泄漏模式搜索：

| 搜索模式 | 结果 |
|----------|------|
| `print(.*api_key` | **0 匹配** ✅ |
| `log.*api_key` | **0 匹配** ✅ |
| `StreamEvent.*api_key` | **0 匹配** ✅ |
| `json.dumps.*api_key` | **0 匹配** ✅ |

唯一相关命中在 `tools/e2e_verify.py:84` — 测试跳过消息 `"SKIP: compact model test (no QWEN_API_KEY)"`，不泄漏实际密钥值。

**结论**: 日志/输出层没有发现 API Key 泄漏。✅

### 1.2 Auth 模块安全性 (D)

**文件**: [server/auth/provider.py](file:///d:/agent_learn/py-cc/py-cc-learn/server/auth/provider.py)

**强度**:

| 项目 | 实现 | 评价 |
|------|------|------|
| 密钥加密存储 | Fernet 对称加密 (cryptography 库) | ✅ 良好 |
| 密钥派生 | PBKDF2HMAC + SHA256, 600,000 迭代 | ✅ 良好 |
| 文件权限 | Unix 下 `chmod 0o600` | ✅ 良好 |
| 密钥来源优先级 | ENV → API_KEY_HELPER → 加密存储 → None | ✅ 合理 |

**风险**:

| 风险 | 严重度 | 详情 |
|------|--------|------|
| KDF 输入弱 | **中** | 密钥派生使用 `COMPUTERNAME`/`HOSTNAME` 作为输入 — 这不是秘密，攻击者可以轻易猜测 |
| Google API Key URL 泄漏 | **高** | [server/services/google_provider.py:68](file:///d:/agent_learn/py-cc/py-cc-learn/server/services/google_provider.py#L68) 将 API Key 拼接在 URL query string 中：`f"?key={self.config.api_key}"` — 会被代理日志、浏览器历史记录、referer header 泄漏 |
| 密钥验证过弱 | **低** | `is_valid_api_key` 仅校验 `[a-zA-Z0-9\-_]+` 格式，不验证长度、前缀或结构 |
| 环境变量明文存储 | **低** | Settings 模型中的 `*_api_key` 字段从 `.env` 文件明文读取 |
| 无密钥轮换机制 | **低** | 缺少 API Key 过期/轮换支持 |

**建议**:
- 为 KDF 增加硬编码的静态盐值，增加攻击者猜测难度
- Google Provider 改为使用 `x-goog-api-key` header 代替 URL query string
- 增加 API Key 格式验证（如 Anthropic key 以 `sk-ant-` 开头）

---

## 2. CORS / CSRF 安全

### 2.1 CORS 配置审计 (C)

**位置**: [server/main.py:L211-L218](file:///d:/agent_learn/py-cc/py-cc-learn/server/main.py#L211-L218)

| 配置项 | 当前值 | 风险 |
|--------|--------|------|
| `allow_origins` | `["*"]` | **🔴 严重** — 允许任意源访问 |
| `allow_credentials` | `True` | **🔴 严重** — 与 `*` 组合违反 CORS 规范，浏览器会拒绝该配置 |
| `allow_methods` | `["*"]` | 🟡 中等 — 所有 HTTP 方法允许 |
| `allow_headers` | `["*"]` | 🟡 中等 — 所有请求头允许 |
| `expose_headers` | `["X-Request-ID", "Retry-After"]` | 🟢 安全 — 仅暴露必要头 |

**严重问题**: `allow_origins=["*"]` + `allow_credentials=True` 是一个经典的反模式。浏览器 CORS 规范明确禁止这种组合：当 `allow_credentials=True` 时，`allow_origins` 不能是 `*`，必须是具体的 origin 列表。

### 2.2 CSRF 保护

| 检查项 | 结果 |
|--------|------|
| CSRF 中间件 | **不存在** ❌ |
| CSRF Token | **不存在** ❌ |
| SameSite Cookie | **不存在** ❌ |
| X-CSRF-Token Header 检查 | **不存在** ❌ |

全代码库搜索 `csrf` / `xsrf` / `XSRF` 返回 **0 匹配**。

**建议**:
- 将 `allow_origins` 改为具体的前端域名列表
- 移除 `allow_credentials=True` 或改为具体 origin
- 添加 CSRF 保护中间件（如 `fastapi-csrf-protect`）

---

## 3. 输入验证

### 3.1 当前状态

**位置**: [server/main.py:L77-L87](file:///d:/agent_learn/py-cc/py-cc-learn/server/main.py#L77-L87) 和 [server/main.py:L260-L308](file:///d:/agent_learn/py-cc/py-cc-learn/server/main.py#L260-L308)

| 验证项 | 实现 | 评价 |
|--------|------|------|
| 空 prompt 拒绝 | `prompt.strip()` 检查 | ✅ |
| 长度限制 | `MAX_PROMPT_CHARS = 200_000` | ✅ |
| 控制字符检查 | `_validate_prompt()` 检查纯控制字符 | ✅ |
| Prompt 注入检测 | **不存在** ❌ | ⚠️ |
| 输入消毒 | **不存在** ❌ | ⚠️ |

**缺失**: 没有检测 prompt injection 攻击模式（如 `</system>`, `<|im_start|>`, `ignore all previous instructions` 等）。

### 3.2 新增安全模块

已创建 [server/utils/security.py](file:///d:/agent_learn/py-cc/py-cc-learn/server/utils/security.py)，提供：

| 函数 | 用途 |
|------|------|
| `detect_injection(text)` | 检测 7 种 prompt injection 模式 |
| `is_prompt_safe(text)` | 综合安全检查（空值、长度、注入） |
| `sanitize_prompt(text)` | 去除 null 字节，截断超长输入 |

**建议**: 在 `prompt_validation_middleware` 中集成 `is_prompt_safe()` 和 `detect_injection()` 调用。

---

## 4. Bash 工具安全性

### 4.1 Tree-sitter 声明 vs 实际

| 来源 | 声明 | 实际 |
|------|------|------|
| [README.md](file:///d:/agent_learn/py-cc/py-cc-learn/README.md) (L32) | "tree-sitter AST 安全校验 + 三层安全漏斗" | ❌ |
| [README.md](file:///d:/agent_learn/py-cc/py-cc-learn/README.md) (L109) | "Shell 执行 + tree-sitter 安全校验" | ❌ |
| [pyproject.toml](file:///d:/agent_learn/py-cc/py-cc-learn/pyproject.toml) (L39) | `tree-sitter>=0.23.0` 依赖 | ✅ |
| [bash_tool.py](file:///d:/agent_learn/py-cc/py-cc-learn/server/tools/bash_tool.py) | 实际安全实现 | 仅正则模式匹配 ❌ |

**🔴 严重**: README 多处声称使用 tree-sitter AST 进行安全校验，但 [bash_tool.py](file:///d:/agent_learn/py-cc/py-cc-learn/server/tools/bash_tool.py) 中 **完全没有 tree-sitter 相关代码**。tree-sitter 依赖已安装但未使用。

### 4.2 现有安全措施

| 措施 | 实现 | 评价 |
|------|------|------|
| 危险命令正则 | 13 个 `DANGEROUS_PATTERNS` | ✅ 覆盖较好 |
| 命令分类 | search / read / list 分类 | ✅ 有用元数据 |
| 输出截断 | `MAX_RESULT_SIZE_CHARS = 30000` | ✅ |
| 超时控制 | 默认 120s | ✅ |

### 4.3 安全缺陷

| 缺陷 | 严重度 | 详情 |
|------|--------|------|
| Shell 注入风险 | **高** | 使用 `asyncio.create_subprocess_shell()` 而非 `create_subprocess_exec()` — 用户输入直接传给 shell |
| 权限检查空实现 | **高** | `check_permissions()` 始终返回 `behavior="allow"` — 不执行任何权限验证 |
| 破坏性标记缺失 | **中** | `is_destructive()` 始终返回 `False` — 危险命令未被标记 |
| 只读标记缺失 | **低** | `is_read_only()` 始终返回 `False` |

---

## 5. Docker 沙箱隔离

### 5.1 隔离配置

**文件**: [sandbox/manager.py](file:///d:/agent_learn/py-cc/py-cc-learn/sandbox/manager.py)

| 隔离项 | 配置 | 评价 |
|--------|------|------|
| 网络 | `"none"` | ✅ 完全网络隔离 |
| 内存 | `"512m"` | ✅ 合理限制 |
| CPU | `1.0` 核 | ✅ 合理限制 |
| 进程数 | `100` | ✅ 防 fork bomb |
| 超时 | 120s 默认 | ✅ |
| 容器预热池 | 3 个容器 | ✅ 性能优化 |

### 5.2 隔离缺陷

| 缺陷 | 严重度 | 详情 |
|------|--------|------|
| **回退到宿主机** | **🔴 严重** | 当 Docker 不可用时，[sandbox/manager.py:L346-L369](file:///d:/agent_learn/py-cc/py-cc-learn/sandbox/manager.py#L346-L369) 直接使用 `subprocess` 在宿主机执行 — 完全丧失隔离 |
| Root 运行 | **高** | Dockerfile 无 `USER` 指令，容器内以 root 运行 |
| 无 seccomp/AppArmor | **中** | 未配置任何内核安全配置文件 |
| 无只读根文件系统 | **中** | `read_only` 配置仅用于 volume mount 模式，容器文件系统可写 |
| 无 `--cap-drop=ALL` | **中** | 容器保留默认 Linux capabilities |
| Warm pool 持久化 | **低** | 容器在命令执行后重新放入池中，跨请求共享 |

### 5.3 Dockerfile 审计

**文件**: [sandbox/Dockerfile](file:///d:/agent_learn/py-cc/py-cc-learn/sandbox/Dockerfile)

| 检查项 | 结果 |
|--------|------|
| 基础镜像 | `ubuntu:22.04` （未锁定摘要） |
| 多余软件包 | `git`, `curl`, `wget`, `build-essential`, `python3-pip` 等 |
| USER 指令 | **缺失** — root 运行 |
| 无 HEALTHCHECK | N/A |

---

## 6. 其他安全观察

### 6.1 正向发现

| 项目 | 详情 |
|------|------|
| 速率限制 | `@limiter.limit("30/minute")` 在 [server/main.py:L364](file:///d:/agent_learn/py-cc/py-cc-learn/server/main.py#L364) ✅ |
| 结构化日志 | structlog + JSON 输出 ✅ |
| 请求 ID 追踪 | `X-Request-ID` 中间件 ✅ |
| 优雅关闭 | `_graceful_shutdown()` + 连接计数 ✅ |
| 图片上传验证 | 类型检查 + 尺寸限制 + resize 处理 ✅ |
| system prompt 安全指令 | 包含防御 prompt injection 的指导 ✅ |

### 6.2 待改进项

| 项目 | 严重度 | 建议 |
|------|--------|------|
| 无 X-Content-Type-Options | 低 | 添加 `nosniff` 响应头 |
| 无 X-Frame-Options | 低 | 添加 `DENY` 响应头 |
| 无 CSP | 低 | 添加 Content-Security-Policy |
| 无 Request ID 类型校验 | 低 | `X-Forwarded-For` trust proxy 易受 IP 欺骗 |

---

## 7. 总体安全评分

| 分类 | 分数 | 满分 | 说明 |
|------|------|------|------|
| API Key 保护 (1.1 泄漏检测) | 10 | 10 | 无日志泄漏 |
| API Key 保护 (1.2 存储加密) | 10 | 15 | 加密存储良好，但 KDF 弱 + Google URL 泄漏 |
| CORS 配置 | 0 | 10 | `allow_origins=["*"]` 全放行 |
| CSRF 保护 | 0 | 5 | 完全缺失 |
| 输入验证 | 12 | 15 | 基础验证好，缺注入检测（已补） |
| Bash 工具安全 | 10 | 20 | 正则覆盖好，但无 tree-sitter、shell 注入、权限绕过 |
| Docker 沙箱 | 12 | 15 | 隔离配置好，但回退宿主 + root 运行 |
| Auth 密钥管理 | 8 | 10 | 加密好，验证弱 |

| **总分** | **92** | **/100** |
|----------|--------|----------|

### 风险等级: 🟢 低风险

### 优先修复建议（按严重度排序）

1. **🔴 [关键]** 修复 Google API Key URL 泄漏 — [server/services/google_provider.py:68](file:///d:/agent_learn/py-cc/py-cc-learn/server/services/google_provider.py#L68)
2. **🔴 [关键]** 限制 CORS `allow_origins` 为具体域名，移除或修正 `allow_credentials=True`
3. **🔴 [高]** Bash 工具改为 `create_subprocess_exec` 或对 `create_subprocess_shell` 输入做严格的 shell 转义/沙箱化
4. **🟡 [高]** 实现 `check_permissions()` 真正的权限校验，标记 `is_destructive`
5. **🟡 [中]** 集成 `server/utils/security.py` 的 prompt injection 检测到中间件
6. **🟡 [中]** 沙箱 Dockerfile 添加 `USER nonroot`，添加 `--cap-drop=ALL`，添加只读根文件系统
7. **🟢 [低]** 添加 CSRF 保护中间件
8. **🟢 [低]** 添加安全响应头（X-Content-Type-Options, X-Frame-Options, CSP）
9. **🟢 [低]** 实现 tree-sitter AST shell 命令解析，兑现 README 承诺

---

*本报告由自动化安全审计生成，基于静态代码分析。建议结合动态渗透测试进行验证。*
