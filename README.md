# py-cc-learn &nbsp;`v0.1.1-pre`

> **AI 编程助手** — Claude Code 架构的 Python 重写 &nbsp;|&nbsp; ⚠️ 预发布版本，仍在积极开发中

基于 [Claude Code Haha](https://github.com/anthropics/claude-code) 源码，使用 **Python 3.12+** (FastAPI) + **Vue 3** (Vite) 完整重写，支持多厂商模型后端。

---

## 🏷️ 版本状态

| 版本 | 状态 | 说明 |
|------|------|------|
| `v0.1.1-pre` | 🟡 预发布 | 核心功能完成，性能调优中 |
| 目标 `v0.2.0` | ⬜ 计划中 | 上下文压缩管线 + 完整恢复机制 |

**当前仍在积极开发中，不保证 API 稳定性。**

---

## ✨ 功能特性

- **多厂商模型支持** — Anthropic / OpenAI / DeepSeek / Google，Provider 抽象层自动检测
- **Web 前端** — Vue 3 + Vite + Pinia，SSE 流式响应，支持 Markdown 渲染、图片粘贴
- **Docker 沙箱** — 容器预热池 + tree-sitter AST 安全校验 + 三层安全漏斗
- **完整工具系统** — Bash / Read / Write / Edit / Glob / Grep / TodoWrite / WebSearch / WebFetch / Agent / Skill / PlanMode
- **权限管道** — 7 种权限模式 + 4 阶段决策管道 + 11 种决策原因
- **Hook 系统** — 27 种事件类型 + 4 种执行类型
- **上下文压缩** — Micro-Compact + Auto-Compact (180K token 阈值)
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
│   │   └── query_engine.py    # QueryEngine + 10 种退出条件
│   ├── tools/                 # 工具系统 (16 个工具)
│   │   ├── bash_tool.py       # Shell 执行 + tree-sitter 安全校验
│   │   ├── file_*.py          # 文件读写编辑
│   │   ├── agent_tool.py      # 子 Agent 系统
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
├── tests/                     # 228 单元/集成/E2E 测试
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
| Phase 10 | 测试 (228 tests) + CI | ✅ |
| Phase 11 | 部署 + 验收 | ✅ |

**49/49 Task 完成 · 293/293 Checklist 通过 · 228 tests passed · v0.1.1-pre**

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

# 源码一致性验证
uv run python tests/verify_models.py
```

---

## 📄 许可证

MIT
