# Memento-X Cloud — 云端中枢 Docker 镜像
FROM python:3.11-slim

LABEL maintainer="Memento-X Team"
LABEL description="Memento-X Cloud Hub — AI intent understanding + task scheduling"

# 系统依赖（gcc + libpq-dev 为 asyncpg 编译所需）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖
COPY cloud/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY cloud/ cloud/
COPY schema/ schema/

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "cloud.main:app", "--host", "0.0.0.0", "--port", "8000"]
