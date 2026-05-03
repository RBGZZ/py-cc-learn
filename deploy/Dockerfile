FROM python:3.12-slim AS builder

WORKDIR /app
RUN pip install uv -i https://mirrors.aliyun.com/pypi/simple/

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY server/ ./server/
COPY sandbox/ ./sandbox/
RUN uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/server ./server
COPY --from=builder /app/sandbox ./sandbox
COPY pyproject.toml README.md ./
COPY frontend/dist ./frontend/dist

ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
