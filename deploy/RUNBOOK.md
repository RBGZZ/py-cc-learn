# py-cc-learn Deployment Runbook

## Quick Start
```bash
# Build and start
docker compose -f deploy/docker-compose.yml up -d --build

# Check health
curl http://localhost:8000/api/v1/health

# View logs
docker compose -f deploy/docker-compose.yml logs -f backend
```

## Configuration

### Required Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek API key | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `GOOGLE_API_KEY` | Google Gemini API key | - |
| `QWEN_API_KEY` | Qwen API key | - |

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | INFO |
| `LOG_FORMAT` | Log format (json/console) | json |
| `CORS_ORIGINS` | Comma-separated allowed origins | localhost:5173,localhost:8000 |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | true |
| `CLAUDE_CODE_PROMPT_CACHING_ENABLED` | Enable Anthropic prompt caching | disabled |
| `EXTENDED_THINKING_ENABLED` | Enable extended thinking | disabled |
| `SSE_IDLE_TIMEOUT_SECONDS` | SSE stream idle timeout | 120 |
| `DISABLE_COMPACT` | Disable auto-compact | disabled |

## Monitoring

### Health Check
```bash
curl http://localhost:8000/api/v1/health
# Expected: {"status":"healthy","uptime_seconds":1234,"version":"1.0.0-rc1"}
```

### Logs
- Application logs: `logs/pycc.log` (JSON format, rotated at 100MB, 5 backups)
- Docker logs: `docker compose logs backend`
- Request tracing: All logs carry `request_id` field

### Key Metrics (from logs)
- `llm_call_complete`: LLM API latency (ttft_ms, total_ms)
- `tool_executed`: Per-tool execution duration
- `compact_complete`: Context compaction duration

## Troubleshooting

### Server won't start
1. Check logs: `docker compose logs backend`
2. Verify API keys are set in `.env`
3. Check port 8000 is not in use: `lsof -i :8000`

### Rate limiting (429 errors)
- Default: 60 req/min globally, 30 req/min for /api/v1/chat
- Reduce request frequency or disable: `RATE_LIMIT_ENABLED=false`

### High memory usage
- Compact reduces context: ensure `DISABLE_COMPACT` is not set
- Restart periodically for long-running sessions

### API errors
- 422: Invalid prompt (empty, too long, or contains injection patterns)
- 429: Rate limited
- 500: Provider unavailable - check API key and connectivity
- 529: Provider overloaded - retry with exponential backoff

## Graceful Shutdown
```bash
docker stop -t 30 py-cc-backend  # 30s timeout for active requests
```
Process: SIGTERM → wait for requests → flush sessions → clean child processes → exit

## Backup & Restore
Session data is stored in memory only. For persistence, mount a volume and configure session storage.
