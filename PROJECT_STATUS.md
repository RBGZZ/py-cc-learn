# py-cc-learn 项目阶段进度

> 最后更新: 2026-05-02
> 下一目标: 完成 Phase 2.5 (T7 Docker) → Phase 3 (T8 Provider / T9 Session) → Phase 4 (T11 核心工具 / T12 QueryEngine / T13 query loop) → MVP

---

## 总体进度

```
Phase 1  ████████████████████ 100%  (T1✅ T2✅ T3✅)
Phase 2  ████████████░░░░░░░░  67%  (T4✅ T5✅ T6✅)
Phase 2.5░░░░░░░░░░░░░░░░░░░░   0%  (T7⏳)
Phase 3  ░░░░░░░░░░░░░░░░░░░░   0%  (T8⏳ T9⏳)
Phase 4  ████░░░░░░░░░░░░░░░░  25%  (T10✅ T11⏳ T12⏳ T13⏳)
Phase 5  ░░░░░░░░░░░░░░░░░░░░   0%  (T14⏳ T15⏳)
Phase 6  ░░░░░░░░░░░░░░░░░░░░   0%  (T16⏳ T17⏳)
Phase 7  ░░░░░░░░░░░░░░░░░░░░   0%  (T18⏳ T19⏳)
Phase 8  ░░░░░░░░░░░░░░░░░░░░   0%  (T20⏳ T21⏳ T22⏳ T22a⏳)
Phase 9  ░░░░░░░░░░░░░░░░░░░░   0%  (T23⏳ T24⏳ T25⏳ T25a-e⏳)
Phase 10 ░░░░░░░░░░░░░░░░░░░░   0%  (T26-T38⏳)
Phase 11 ░░░░░░░░░░░░░░░░░░░░   0%  (T39-T41b⏳)

总进度: 7/42 Task 完成 (17%)
```

---

## 已完成 Task 详情

### ✅ Task 1: Python 项目骨架

| 文件 | 状态 | 说明 |
|------|------|------|
| `pyproject.toml` | ✅ | Pydantic v2 / FastAPI / httpx / tiktoken / structlog / docker-py / slowapi / Pillow / click / tree-sitter / cryptography |
| `.env.example` | ✅ | 4 厂商 API Key + API timeout 600000ms + log level + host/port |
| `.gitattributes` | ✅ | `* text=auto` + `.py/.ts/.vue/.sh/.json/.toml/.yaml/.yml/.md` = `eol=lf` + `.jsonl` = `binary` |
| `.pre-commit-config.yaml` | ✅ | ruff + ruff-format (server/) + prettier (frontend/) |
| `server/main.py` | ✅ | FastAPI lifespan + CORS + `/api/v1/health` + `/api/v1/status` |
| `server/` 目录结构 | ✅ | engine/ tools/ services/ state/ utils/ models/ auth/ commands/ prompts/ |
| `sandbox/` | ✅ | 仅 `__init__.py`，Dockerfile + manager.py 待 T7 |
| `deploy/` | ⚠️ | 尚未创建，待 T40 |
| `tests/` 目录 | ✅ | unit/ integration/ e2e/ 子目录已创建 |

### ✅ Task 2: 核心数据模型 (Pydantic v2)

| 文件 | 行数 | 内容 |
|------|------|------|
| `models/messages.py` | ~195 | Message、ContentBlock（Text/ToolUse/ToolResult/Image/Thinking/RedactedThinking）、UserMessage、AssistantMessage、SystemMessage、ProgressMessage、AttachmentMessage、StreamEvent、CompactBoundary、APIError、StopHookInfo 等 20+ 类 |
| `models/tools.py` | ~45 | ToolResult、ToolUseContext、ValidationResult、ToolInputJSONSchema |
| `models/tasks.py` | ~115 | TaskType (7 种)、TaskStatus (5 态)、生成 task_id、TaskStateBase、TaskHandle、TaskContext、LocalShellSpawnInput |
| `models/permissions.py` | ~220 | 7 种 PermissionMode、PermissionRule(allow/deny/ask)、PermissionUpdate(6 种)、PermissionDecision(allow/ask/deny)、PermissionPassthrough、ToolPermissionContext |
| `models/sdk.py` | ~415 | SDKMessage 联合类型(25+)、SDKResultSuccess/Error、ApiKeySource、ModelUsage、RateLimitInfo、Hook 消息、Task 消息、Session 消息 |

### ✅ Task 3: 全局状态管理

| 文件 | 行数 | 内容 |
|------|------|------|
| `state/global_state.py` | ~1140 | GlobalState 单例（~80 字段 + ~130 getter/setter）、session_id、project_root、cwd、total_cost_usd、model_usage、lines_added/removed、token 统计、latch 字段、prompt cache、hook 注册、skills、slow operations 等 |
| `state/app_state.py` | ~36 | AppState Pydantic 模型（messages、is_processing、current_model、permission_mode、todos、tasks、mcp_tools 等） |

### ✅ Task 4: 配置管理与认证

| 文件 | 行数 | 内容 |
|------|------|------|
| `utils/settings.py` | ~95 | pydantic-settings：4 厂商 API Key/Model、API timeout(600s)、log level、host/port |
| `auth/provider.py` | ~195 | ApiKeyStore（Fernet 加密）、get_anthropic_api_key 优先级链、OpenAI/DeepSeek/Google Key |

### ✅ Task 5: 通用工具函数

| 文件 | 行数 | 内容 |
|------|------|------|
| `utils/abort.py` | ~180 | AbortController (asyncio.Event + weakref 传播)、create_child_abort_controller、wait_for_with_abort、force_kill_process (SIGTERM→2s→SIGKILL) |
| `utils/shell.py` | ~470 | ShellType(BASH/POWERSHELL)、ShellProvider 基类、BashShellProvider、PowerShellShellProvider、find_suitable_shell、exec_command (双 Shell 架构)、set_cwd |
| `utils/messages.py` | ~290 | INTERRUPT/CANCEL/REJECT 消息常量、create_user_message、create_assistant_message、filter_real_messages、normalize_content、SYNTHETIC_MESSAGES |
| `utils/tokens.py` | ~190 | tiktoken 集成 (cl100k_base/o200k_base)、@lru_cache(maxsize=8)、count_tokens/messages、get_token_usage、token_count_with_estimation |
| `utils/platform.py` | ~169 | get_platform (Windows/WSL/macOS/Linux)、get_wsl_version、get_linux_distro_info、is_msys/is_cygwin、get_windows_subtype、detect_vcs |
| `utils/log.py` | ~230 | structlog JSON/Console 输出、RotatingFileHandler (100MB×5)、ErrorLogSink、request_id 注入、setup_logging |

### ✅ Task 6: Windows 平台适配

| 文件 | 行数 | 内容 |
|------|------|------|
| `utils/windows_paths.py` | ~125 | windows_to_posix_path/posix_to_windows_path (LRU-500)、find_git_bash_path (memoized)、check_path_exists、find_executable |
| `utils/shell/discovery.py` | ~90 | find_power_shell_path (pwsh→powershell + snap规避)、get_cached_power_shell_path (竞态安全)、get_power_shell_edition、is_msys/is_cygwin |
| `utils/shell/bash_provider.py` | ~125 | create_bash_shell_provider (POSIX 路径化、2>nul→2>/dev/null、heredoc 处理、stdin redirect 检测) |
| `utils/shell/powershell_provider.py` | ~85 | create_power_shell_provider (-NoProfile -NonInteractive -EncodedCommand Base64 UTF-16LE、$LASTEXITCODE 优先) |
| `utils/browser.py` | ~80 | open_browser (rundll32 url,OpenURL + HTTP 校验)、open_path (explorer/open/xdg-open) |
| `utils/graceful_shutdown.py` | ~28 | terminate_process_tree (taskkill /F /T /PID + POSIX SIGTERM→SIGKILL) |
| `utils/editor.py` | ~125 | get_external_editor (VISUAL→EDITOR→code/vi/nano)、classify_gui_editor、open_file_in_external_editor (Windows shell=True) |
| `utils/clipboard.py` | ~100 | get_image_from_clipboard (powershell Get-Clipboard Image / osascript PNGf / xclip/wl-paste) |
| `utils/sleep_preventer.py` | ~80 | start/stop_prevent_sleep (SetThreadExecutionState + caffeinate -i 300s timer) |
| `utils/file_utils.py` | ~75 | get_temp_dir (%TEMP%)、get_appdata/session_storage_dir (%APPDATA%)、normalize_path_for_comparison (NTFS lower)、get_write_flags (Windows 'w')、get_last_separator_index (/+\) |
| `utils/hooks_windows.py` | ~45 | make_to_hook_path (bash→POSIX / powershell→原生)、auto_prepend_bash (.sh→bash 前缀)、should_skip_shell_prefix/env_file |

### ✅ Task 10: Tool 基类接口

| 文件 | 行数 | 内容 |
|------|------|------|
| `tools/tool.py` | ~690 | Tool ABC（~40 属性和方法）、ToolCallResult、ToolDef、buildTool（7 种默认值填充）、tool_matches_name、find_tool_by_name |
| `tools/registry.py` | ~195 | assembleToolPool（localeCompare + uniqBy 内置优先）、filter_tools_by_deny_rules、get_tools、get_merged_tools |
| `tools/streaming.py` | ~630 | StreamingToolExecutor（4 态 queued→executing→completed→yielded）、sibling abort (仅 Bash 错误触发)、progress buffer、deferred context modifier |

---

## 上次代码审查结果 (2026-05-02)

| 类别 | 数量 | 状态 |
|------|------|------|
| 🔴 Critical Bug | 2 | ✅ 已修复 (B023 闭包变量 / BashShellProvider.detached) |
| 🟡 Medium Bug | 3 | ✅ 已修复 (未使用变量 / 命名规范 / 缺失 f-string) |
| 🟢 Lint 警告 | 678→53 | ✅ 已修复→剩余为风格警告(无功能性) |
| 语法检查 | 41 文件 | ✅ 全部通过 |

### 已知设计注意点

1. **双重 ShellProvider**: `utils/shell.py`（简洁版）和 `utils/shell/bash_provider.py`（完整版）并存，后续需整合
2. **双重 AbortController**: `utils/abort.py`（weakref 传播）和 `tools/streaming.py`（sibling abort）各有实现，API 不同但互补
3. **`__init__.py` 导出**: 各包导出为空，后续 Task 需补充
4. **camelCase 字段**: Pydantic 模型中保留以匹配 JSON 协议，使用 `populate_by_name=True`

---

## 下一步执行计划

按依赖链顺序：

```
Step 1 (串行·解瓶颈)
└── T7 Docker 沙箱 ← 阻塞 T8/T11

Step 2 (并行·3 方向)
├── T8+T9 Provider + Session ← 依赖 T4+T2+T3+T7
├── T11 核心工具 (9个)      ← 依赖 T5+T10+T7
└── T14 权限 + T20 前端     ← 依赖 T2 / T1（可立即启动）
```

| Task | 状态 | 优先级 | 估计工作量 | 依赖 |
|------|------|--------|-----------|------|
| T7 | ⏳ 即将启动 | 🔴 最高 | 大 | T6 ✅ |
| T8 | ⏳ 等待 T7 | 🔴 高 | 大 | T4 ✅, T7 |
| T9 | ⏳ 等待 T2 | 🔴 高 | 中 | T2 ✅, T3 ✅ |
| T11 | ⏳ 等待 T7 | 🔴 高 | 大 | T5 ✅, T7, T10 ✅ |
| T14 | ⏳ 可启动 | 🟡 中 | 中 | T2 ✅ |
| T20 | ⏳ 可启动 | 🟡 中 | 中 | T1 ✅ |
| T12+T13 | ⏳ 等待 T8 | 🔴 最高 | 极大 | T3 ✅, T8, T9, T10 ✅, T12 |

---

## 文件清单（按 Task 分组）

```
py-cc-learn/
├── .env.example                    [T1]
├── .gitattributes                  [T1]
├── .pre-commit-config.yaml         [T1]
├── .gitignore                      [T1]
├── pyproject.toml                  [T1]
├── README.md
├── PROJECT_STATUS.md               [本文档]
├── uv.lock
├── sandbox/
│   └── __init__.py                 [T1]
├── deploy/                         [待 T40]
├── frontend/                       [待 T20]
├── tests/
│   ├── __init__.py                 [T1]
│   ├── conftest.py                 [待 T26]
│   ├── e2e/__init__.py             [T1]
│   ├── integration/__init__.py     [T1]
│   └── unit/__init__.py            [T1]
└── server/
    ├── __init__.py                 [T1]
    ├── main.py                     [T1]
    ├── auth/
    │   ├── __init__.py             [T1]
    │   └── provider.py             [T4]
    ├── commands/
    │   └── __init__.py             [T1]
    ├── engine/
    │   └── __init__.py             [T1]
    ├── models/
    │   ├── __init__.py             [T1]
    │   ├── messages.py             [T2]
    │   ├── permissions.py          [T2]
    │   ├── sdk.py                  [T2]
    │   ├── tasks.py                [T2]
    │   └── tools.py                [T2]
    ├── prompts/
    │   └── __init__.py             [T1]
    ├── services/
    │   └── __init__.py             [T1]
    ├── state/
    │   ├── __init__.py             [T1]
    │   ├── app_state.py            [T3]
    │   └── global_state.py         [T3]
    ├── tools/
    │   ├── __init__.py             [T1]
    │   ├── registry.py             [T10]
    │   ├── streaming.py            [T10]
    │   └── tool.py                 [T10]
    └── utils/
        ├── __init__.py             [T1]
        ├── abort.py                [T5]
        ├── browser.py              [T6]
        ├── clipboard.py            [T6]
        ├── editor.py               [T6]
        ├── file_utils.py           [T6]
        ├── graceful_shutdown.py    [T6]
        ├── hooks_windows.py        [T6]
        ├── log.py                  [T5]
        ├── messages.py             [T5]
        ├── platform.py             [T5/T6]
        ├── settings.py             [T4]
        ├── shell.py                [T5]
        ├── sleep_preventer.py      [T6]
        ├── tokens.py               [T5]
        ├── windows_paths.py        [T6]
        └── shell/
            ├── __init__.py         [T6]
            ├── bash_provider.py    [T6]
            ├── discovery.py        [T6]
            └── powershell_provider.py [T6]
```

---

## 统计

| 指标 | 数值 |
|------|------|
| 已实现文件数 | 41 个 Python 文件 + 5 个配置文件 |
| 已实现代码行数 | ~7,500 行 |
| 已完成 Task | 7 个 (T1-T6 + T10) |
| 待完成 Task | 35 个 |
| Lint 错误 | 0 functional / 53 style-only |
| 语法状态 | 全部通过 |
