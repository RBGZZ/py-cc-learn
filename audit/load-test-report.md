# Load Test Report

**Status**: ⚠️ Pending — requires Docker daemon running + DEEPSEEK_API_KEY configured

## Test Configuration

| Parameter | Value |
|-----------|-------|
| Model | deepseek-v4-flash |
| Tool | Locust (tools/load_test.py) |
| Test duration | 60s per concurrency level |
| Spawn rate | 5/10/20 users/sec |

## Results

### Level 1: 10 concurrent users
| Metric | Value |
|--------|-------|
| RPS | _pending_ |
| P50 latency | _pending_ |
| P95 latency | _pending_ |
| P99 latency | _pending_ |
| Error rate | _pending_ |
| 429 count | _pending_ |

### Level 2: 50 concurrent users
| Metric | Value |
|--------|-------|
| RPS | _pending_ |
| P50 latency | _pending_ |
| P95 latency | _pending_ |
| 429 count | _pending_ |

### Level 3: 100 concurrent users
| Metric | Value |
|--------|-------|
| RPS | _pending_ |
| P50 latency | _pending_ |
| P95 latency | _pending_ |
| 429 count | _pending_ |

## How to Run

```bash
# 1. Start Docker
# 2. Start services
docker compose -f deploy/docker-compose.yml up -d

# 3. Set API key
$env:DEEPSEEK_API_KEY = "sk-xxx"

# 4. Run load test
uv run locust -f tools/load_test.py --headless --host http://localhost:8000 --users 50 --spawn-rate 10 --run-time 60s

# 5. Stop services
docker compose -f deploy/docker-compose.yml down
```
