FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.13.6
COPY pyproject.toml uv.lock ./
COPY backend ./backend
ARG WITH_SEMANTIC=false
RUN if [ "$WITH_SEMANTIC" = "true" ]; then uv sync --frozen --no-dev --extra semantic; else uv sync --frozen --no-dev; fi
RUN useradd --uid 10001 --create-home lists
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"]
CMD ["/app/.venv/bin/uvicorn", "lists_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers", "--timeout-keep-alive", "5", "--limit-concurrency", "32"]
