# py-cc-learn &nbsp;`v0.3.0`

> **AI 编程助手** — Claude Code 架构的 Python 重写 &nbsp;|&nbsp; ⚠️ 预发布版本，仍在积极开发中

基于 [Claude Code Haha](https://github.com/anthropics/claude-code) 源码，使用 **Python 3.12+** (FastAPI) + **Vue 3** (Vite) 完整重写，支持多厂商模型后端。

---

## 🏷️ 版本状态

| 版本 | 状态 | 说明 |
|------|------|------|
| `v0.3.0` | ✅ 生产就绪 | 44/44 audit gaps resolved, 238 tests |
| `v0.2.1` | ✅ 已发布 | streaming fallback, PTL recovery, token budget |
| `v0.2.0` | ✅ 已发布 | compact pipeline, AgentTool, permission UI |
| `v0.1.3` | ✅ 已发布 | production audit complete (44 gaps identified) |
| 目标 `v1.0` | ⬜ 计划中 | 需求评审 + 多模态

**当前仍在积极开发中，不保证 API 稳定性。**

---

## ✨ 功能特性

- **多厂商模型支持** — Anthropic / OpenAI / DeepSeek / Google，Provider 抽象层自动检测
- **Web 前端** — Vue 3 + Vite + Pinia，SSE 流式响应，支持 Markdown 渲染、图片粘贴
- **Docker 沙箱** — 容器预热池 + tree-sitter AST 安全校验 + 三层安全漏斗
- **完整工具系统** — Bash / Read / Write / Edit / Glob / Grep / TodoWrite / WebSearch / WebFetch / Agent / Skill / PlanMode
- **并行工具执行** — StreamingToolExecutor 流式并行调度，并发安全工具同时执行，非并发工具保持串行
- **流式工具启动** — 模型 SSE 输出中即刻排队工具执行，降低首字延迟
- **错误恢复管线** — max_output_tokens 升级+多次恢复 / 模型 fallback 自动切换 / missing tool_result 合成
- **权限管道** — 7 种权限模式 + 4 阶段决策管道 + 11 种决策原因
- **Hook 系统** — 27 种事件类型 + Post-sampling / Stop hooks 可注册 API
- **上下文压缩** — Auto-Compact (180K token 阈值) + compact_boundary_index
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
├── tests/                     # 237 单元/集成/E2E 测试
├── tools/                     # 性能基准测试
├── audit/                     # TS 源码对比审计报告
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

**49/49 Task 完成 · 293/293 Checklist 通过 · 238 tests passed · v0.3.0**

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

# 冷启动性能基准
uv run python tools/benchmark_cold_start.py

# 内存泄漏检测
uv run python tools/benchmark_memory.py

# E2E 集成验证（需 API Key）
uv run python tools/e2e_verify.py

# 源码一致性验证
uv run python tests/verify_models.py
```

---

## 🔍 生产就绪审计

本版本完成了一次完整的 TS 源码逐模块对比审计（[audit/gaps.md](audit/gaps.md)），覆盖 5 个维度：

| 模块 | 审计范围 | 差异数 | P0 修复 |
|------|----------|--------|---------|
| 引擎层 | `query_engine.py` vs `query.ts` (1729行) | 14 | 3 已修 |
| 工具系统 | 20 Python vs 45+ TS tools | 7 | 已标注 |
| 服务层 | Provider / MCP / LSP / Compact | API 对齐 | — |
| 基础设施 | State / Config / Auth / Messages | 对齐 | — |
| 前端 | Vue 3 vs React/Ink 组件 | 20 | 计划 v0.2.0 |

**性能基准实测**：

| 指标 | 结果 | 目标 |
|------|------|------|
| 冷启动 | 0.47s | ≤ 5s ✅ |
| 4xRead 并行 | 0.12s | ≤ 0.2s ✅ |
| 混合批执行 | 0.83s | ≤ 1.0s ✅ |
| 内存泄漏 (500轮) | 5.3MB | ≤ 500MB ✅ |
| E2E 单轮对话 (DeepSeek v4) | "Hello! How can I assist you today?" | completed ✅ |

---

## 📄 许可证

MIT
