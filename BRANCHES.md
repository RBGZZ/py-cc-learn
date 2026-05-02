# Git 分支与版本策略

## 阶段性 Tag

| Tag | Phase | 内容 |
|-----|-------|------|
| `v0-phase1` | Phase 1 | 项目骨架 + Pydantic 数据模型 + GlobalState |
| `v0-phase2` | Phase 2 | Windows 平台适配 + 通用工具函数 |
| `v0-phase3` | Phase 2.5-3 | Docker 沙箱 + 多厂商 Provider + 会话持久化 |
| `v0-phase4` | Phase 4 | **MVP 里程碑**：Tool 基类 + 核心工具 + QueryEngine + Query Loop |
| `v0-phase5` | Phase 5-6 | 权限 + Hook + 系统提示词 + 上下文压缩 |
| `v0-phase6` | Phase 7-8 | 子 Agent + 扩展工具 + Vue 3 前端 |
| `v0-phase7` | Phase 9 | FastAPI 路由 + CLI + Git + 图像 + LSP + MCP |
| `v1.0` | Phase 10-11 | 测试全覆盖 + CI + 部署 + 验收 |

## 打标签命令

```bash
git tag -a v0-phase1 -m "Phase 1: Project skeleton, data models, GlobalState"
git tag -a v0-phase2 -m "Phase 2: Windows adapt, utility modules"
git tag -a v0-phase3 -m "Phase 3: Docker sandbox, multi-vendor provider, sessions"
git tag -a v0-phase4 -m "Phase 4: MVP - Tool base, core tools, QueryEngine, Query Loop"
git tag -a v0-phase5 -m "Phase 5: Permissions, Hooks, system prompts, compaction"
git tag -a v0-phase6 -m "Phase 6: Sub-agent, extension tools, Vue 3 frontend"
git tag -a v0-phase7 -m "Phase 7: FastAPI, CLI, Git, Image, LSP, MCP, CORS"
git tag -a v1.0 -m "v1.0: Full test coverage, CI, deploy, acceptance"
git push --tags
```

## 分支策略

- `main` — 稳定分支，每个 Phase 合并后打 tag
- `develop` — 开发分支（如需协作）
- 不强制 feature 分支，单人开发直接 push main
