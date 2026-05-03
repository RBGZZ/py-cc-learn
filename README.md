# py-cc-learn &nbsp;`v0.4.0`

> **AI 编程助手** — Claude Code 架构的 Python 重写 &nbsp;|&nbsp; 5 厂商 Provider &nbsp;|&nbsp; 295 tests

基于 [Claude Code Haha](https://github.com/anthropics/claude-code) 源码，使用 **Python 3.12+** (FastAPI) + **Vue 3** (Vite) 完整重写，支持多厂商模型后端。

---

## 🏷️ 版本状态

| 版本 | 状态 | 说明 |
|------|------|------|
| `v0.3.5` | ✅ 最新 | 性能全面完善：Token Budget重写 / Prompt Caching / Extended Thinking / P1修复 |
| `v0.3.4` | ✅ 已发布 | 性能测试缺口补齐 + 深度性能审计（43 gaps, 14 P0 已修复） |
| `v0.3.3` | ✅ 已发布 | 性能基线对齐：HTTP客户端复用 / tiktoken统一 / slowapi限流 |
| `v0.3.2` | ✅ 已发布 | 测试迭代2 (+21 tests, 274→295) + compact model |
| `v0.3.1` | ✅ 已发布 | Qwen 适配 + 多 Provider 测试 + E2E 通过 |
| `v0.3.0` | ✅ 已发布 | 44/44 audit gaps resolved, 生产就绪 |
| `v0.2.1` | ✅ 已发布 | streaming fallback, PTL recovery, token budget |
| `v0.2.0` | ✅ 已发布 | compact pipeline, AgentTool, permission UI |
| 目标 `v1.0` | ⬜ 计划中 | 多模态 + 需求评审

**当前仍在积极开发中，不保证 API 稳定性。**

---

## ✨ 功能特性

- **多厂商模型支持** — Anthropic / OpenAI / DeepSeek / Google / Qwen，Provider 抽象层自动检测
- **Web 前端** — Vue 3 + Vite + Pinia，SSE 流式响应，权限对话框、Markdown 渲染、图片粘贴
- **Docker 沙箱** — 容器预热池 + tree-sitter AST 安全校验 + 三层安全漏斗
- **完整工具系统** — Bash / Read / Write / Edit / Glob / Grep / TodoWrite / WebSearch / WebFetch / Agent / Skill / PlanMode
- **并行工具执行** — StreamingToolExecutor 流式并行调度，并发安全工具同时执行，非并发工具保持串行
- **流式工具启动** — 模型 SSE 输出中即刻排队工具执行，降低首字延迟
- **错误恢复管线** — max_output_tokens 升级+多次恢复 / 模型 fallback 自动切换 / missing tool_result 合成
- **权限管道** — 7 种权限模式 + 4 阶段决策管道 + 11 种决策原因
- **Hook 系统** — 27 种事件类型 + Post-sampling / Stop hooks 可注册 API
- **上下文压缩** — Auto-Compact (180K token 阈值) + Reactive Compact + Context Collapse + compact_boundary_index
- **Prompt Caching** — Anthropic prompt-caching-2024-07-31 beta，系统提示词 + 消息前缀缓存
- **Extended Thinking** — Anthropic thinking.budget_tokens 支持，流式 thinking 事件解析
- **CLI 入口** — `python -m server.cli` 兼容 `--model` / `--resume` / `--cwd`
- **结构化日志** — structlog + RotatingFileHandler + request_id 全链路追踪
- **优雅关闭** — SIGTERM → 等待请求 → 清理子进程 → flush session → 退出

---

## 🚀 快速启动

### 前提条件

- Python 3.12+
- Node.js 20+
- Git
- Docker Desktop（可选，用于沙箱隔离）

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/RBGZZ/py-cc-learn.git
cd py-cc-learn

# 2. 安装 Python 依赖
uv sync

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env，填入以下任一 Key：
#   DEEPSEEK_API_KEY=sk-xxx
#   ANTHROPIC_API_KEY=sk-ant-xxx
#   OPENAI_API_KEY=sk-xxx
#   GOOGLE_API_KEY=xxx
#   QWEN_API_KEY=sk-xxx

# 4. 安装前端依赖并构建
cd frontend
npm install
npm run build
cd ..
```

### 启动

```bash
# 开发模式
uv run uvicorn server.main:app --reload --port 8000

# CLI 模式
uv run python -m server.cli --prompt "Hello" --model deepseek-v4-flash
```

浏览器打开 `http://localhost:8000` 即可使用。

---

## 📦 项目架构

```
py-cc-learn/
├── server/                    # Python 后端 (FastAPI)
│   ├── main.py                # 应用入口，SSE 端点，中间件
│   ├── cli.py                 # CLI 入口
│   ├── engine/                # Agent 引擎层
│   │   └── query_engine.py    # QueryEngine + 11 退出条件 + 流式并行工具执行
│   ├── tools/                 # 工具系统 (16 个工具)
│   │   ├── bash_tool.py       # Shell 执行 + tree-sitter 安全校验
│   │   ├── file_*.py          # 文件读写编辑
│   │   ├── agent_tool.py      # 子 Agent 系统
│   │   ├── streaming.py        # StreamingToolExecutor 并行调度
│   │   └── ...
│   ├── services/              # 服务层
│   │   ├── provider.py        # Provider 抽象基类
│   │   ├── anthropic_provider.py
│   │   ├── openai_provider.py
│   │   ├── deepseek_provider.py
│   │   ├── qwen_provider.py    # 通义千问 Provider (OpenAI 兼容)
│   │   ├── lsp.py             # LSP 语言服务器集成
│   │   ├── mcp.py             # MCP 协议集成
│   │   ├── permissions.py     # 权限决策管道
│   │   ├── hooks.py           # 27 种 Hook 事件
│   │   ├── compact.py         # 上下文压缩管线
│   │   ├── retry.py           # 重试 + 熔断器
│   │   └── errors.py          # 错误分类映射
│   ├── models/                # Pydantic v2 数据模型
│   ├── prompts/               # 系统提示词引擎
│   ├── state/                 # GlobalState + Session 持久化
│   ├── commands/              # 斜杠命令系统
│   ├── auth/                  # API Key 安全存储 (fernet + PBKDF2)
│   └── utils/                 # 工具函数
│       ├── git.py             # Git 集成
│       ├── shell.py           # 双 Shell 架构 (Bash/PowerShell)
│       ├── platform.py        # 跨平台检测
│       ├── windows_paths.py   # Windows 路径转换
│       └── ...
├── frontend/                  # Vue 3 Web 前端
│   └── src/
│       ├── components/        # 11 个核心组件
│       ├── stores/            # Pinia 状态管理
│       └── utils/             # SSE 连接 + 剪贴板
├── sandbox/                   # Docker 沙箱
│   ├── Dockerfile             # ubuntu:22.04 + 开发工具
│   └── manager.py             # 容器预热池管理
├── deploy/                    # 部署配置
│   ├── claude-code.service    # systemd
│   ├── nginx.conf             # 反向代理
│   ├── docker-compose.yml     # 容器编排
│   └── README.md              # 部署指南
├── tests/                     # 295 单元/集成/E2E 测试
├── tools/                     # 10 个性能基准 + E2E + 多 Provider 测试
├── audit/                     # TS 源码对比审计 (44/44 + 性能审计 43 gaps)
├── .trae/specs/python-rewrite/ # 技术规格文档
└── .github/workflows/         # CI 跨平台矩阵
```

---

## 📊 项目进度

| Phase | 名称 | 状态 |
|-------|------|------|
| Phase 1 | 项目基础设施 | ✅ |
| Phase 2 | 基础设施层 + Windows 适配 | ✅ |
| Phase 2.5 | Docker 沙箱 | ✅ |
| Phase 3 | 多厂商 Provider + 会话持久化 | ✅ |
| Phase 4 | Agent 引擎 + Query Loop | ✅ |
| Phase 5 | 权限与 Hook 系统 | ✅ |
| Phase 6 | 系统提示词 + 上下文压缩 | ✅ |
| Phase 7 | 子 Agent + 扩展工具 | ✅ |
| Phase 8 | Vue 3 Web 前端 | ✅ |
| Phase 9 | FastAPI 路由 + CLI + Git + 图像 + LSP + MCP | ✅ |
| Phase 10 | 测试 (238 tests) + CI | ✅ |
| Phase 11 | 部署 + 验收 | ✅ |
| Phase 12 | 性能对齐 TS 参考 (6 gaps) | ✅ |
| Phase 13 | 生产就绪审计 (44 gaps) | ✅ |
| Phase 14 | 审计差距修复 (44/44 resolved) | ✅ |
| Phase 15 | Qwen 适配 + 多 Provider 测试 | ✅ |
| Phase 16 | 测试迭代 (+36 tests, 238 → 274) | ✅ |
| Phase 17 | 性能基线对齐 (HTTP复用/tiktoken/限流/基准) | ✅ |
| Phase 18 | 性能测试缺口补齐 (6 项新基准) | ✅ |
| Phase 19 | 深度性能审计 (6 模块, 43 gaps, 14 P0 修复) | ✅ |
| Phase 20 | 性能全面完善 (TokenBudget/PromptCaching/ExtendedThinking/P1修复) | ✅ |

**79/79 Task 完成 · 352/352 Checklist 通过 · 295 tests passed · v0.3.5**

---

## 🔧 API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/v1/health` | 健康检查 |
| `GET` | `/api/v1/status` | 状态/用量查询 |
| `POST` | `/api/v1/chat` | SSE 流式聊天 |
| `POST` | `/api/v1/stop/{id}` | 停止会话 |
| `POST` | `/api/v1/upload/image` | 图片上传 (≤5MB) |

---

## 🧪 测试

```bash
# 运行全部测试
uv run pytest tests/ -q

# 覆盖率报告
uv run pytest tests/ --cov=server --cov-report=term

# 并行工具执行性能基准
uv run python tools/benchmark_real.py

# 指定 Provider 基准测试
uv run python tools/benchmark_real.py --provider qwen

# 全部 Provider E2E 测试
uv run python tools/test_providers.py

# 单 Provider E2E 验证（需 API Key）
uv run python tools/e2e_verify.py qwen

# 冷启动性能基准
uv run python tools/benchmark_cold_start.py

# 内存泄漏检测
uv run python tools/benchmark_memory.py

# 多轮对话基准
uv run python tools/benchmark_multiturn.py

# Compact 管线基准
uv run python tools/benchmark_compact.py

# Provider 故障恢复基准
uv run python tools/benchmark_resilience.py

# 大上下文基准
uv run python tools/benchmark_large_context.py

# SSE 解析基准
uv run python tools/benchmark_sse_parse.py

# 并发负载测试 (需先启动服务)
uv run locust -f tools/load_test.py --users 50 --spawn-rate 10

# 源码一致性验证
uv run python tests/verify_models.py
```

---

## 🔍 生产就绪审计

本版本完成了一次完整的 TS 源码逐模块对比审计（[audit/gaps.md](audit/gaps.md)），覆盖 5 个维度：

| 模块 | 审计范围 | 差异数 | 状态 |
|------|----------|--------|------|
| 引擎层 | `query_engine.py` vs `query.ts` (1729行) | 14 | ✅ 已修复 |
| 工具系统 | 20 Python vs 45+ TS tools | 7 | ✅ 已修复 |
| 服务层 | Provider / MCP / LSP / Compact | — | ✅ 对齐 |
| 基础设施 | State / Config / Auth / Messages | — | ✅ 对齐 |
| 前端 | Vue 3 vs React/Ink 组件 | 20 | ✅ 已修复 |

**全部 44 条差异已修复，详见 [audit/gaps.md](audit/gaps.md)**。
**性能审计 43 条差距已识别，14 条 P0 已修复，详见 [audit/perf-gaps.md](audit/perf-gaps.md)**。

**性能基准实测**：

| 指标 | 结果 | 目标 |
|------|------|------|
| 冷启动 | 0.49s | ≤ 5s ✅ |
| 4xRead 并行 | 0.12s | ≤ 0.2s ✅ |
| 混合批执行 | 0.83s | ≤ 1.0s ✅ |
| 内存泄漏 (500轮) | 5.3MB | ≤ 500MB ✅ |
| Uvicorn 启动 | 0.54s | ≤ 3s ✅ |
| 多轮对话 (50轮) | 0.10ms/轮 | ≤ 10ms/轮 ✅ |
| Compact 管线 (180K tokens) | 71ms | ≤ 500ms ✅ |
| CircuitBreaker 恢复 | 602ms | ≤ 5s ✅ |
| 大上下文 (150K tokens) | 11ms | ≤ 1s ✅ |
| SSE 解析 (100KB) | 63.4 MB/s | ≥ 1 MB/s ✅ |
| Qwen E2E 单轮对话 | "Hello! How can I assist you today?" | completed ✅ |
| DeepSeek E2E 单轮对话 | "Hello! How can I assist you today?" | completed ✅ |

---

## 📄 许可证

MIT
