# Build context: repository root (the bot reads catalog/pricing from /shared).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    SHARED_DIR=/app/shared DATABASE_URL=sqlite+aiosqlite:////data/tgshop.db
WORKDIR /app/bot

COPY bot/pyproject.toml bot/README.md ./
COPY bot/tgshop ./tgshop
RUN pip install . && useradd --create-home --uid 10001 app && mkdir /data && chown app /data
COPY shared /app/shared

USER app
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8080/api/health').status != 200)"
CMD ["python", "-m", "tgshop", "--mode", "all"]
