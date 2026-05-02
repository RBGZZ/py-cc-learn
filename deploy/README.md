# py-cc-learn 部署指南

## 环境要求

- Python 3.12+
- Node.js 20+ (前端构建)
- Docker Desktop (沙箱模式，可选)
- Git

## 快速启动

```bash
# 1. 安装 Python 依赖
cd py-cc-learn
uv sync

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY 或 OPENAI_API_KEY

# 3. 安装前端依赖并构建
cd frontend
npm install
npm run build
cd ..

# 4. 启动服务
uv run uvicorn server.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000` 即可使用。

## Docker 沙箱模式（可选）

```bash
# 确保 Docker Desktop 已安装并运行
docker build -t py-cc-sandbox sandbox/
```

沙箱不可用时自动回退到宿主机 subprocess 执行。

## 生产部署

### systemd

```bash
sudo cp deploy/claude-code.service /etc/systemd/system/
sudo systemctl enable claude-code
sudo systemctl start claude-code
```

### Docker Compose

```bash
export ANTHROPIC_API_KEY=your-key
docker compose -f deploy/docker-compose.yml up -d
```

### nginx 反向代理

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/claude-code.conf
sudo nginx -t && sudo systemctl reload nginx
```

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/status` | 状态/用量查询 |
| POST | `/api/v1/chat` | SSE 流式聊天 |
| POST | `/api/v1/stop/{id}` | 停止会话 |
| POST | `/api/v1/upload/image` | 图片上传 (≤5MB) |

## CLI 入口

```bash
uv run python -m server.cli --help
uv run python -m server.cli --prompt "Hello" --model claude-sonnet-4-20250514
```
