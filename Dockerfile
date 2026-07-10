# Memento-X Cloud — 云端中枢 Docker 镜像
#
# 构建：
#   docker build -t memento-cloud:latest .
#
# 运行：
#   docker run -d --name memento-cloud \
#     -p 8000:8000 \
#     -e DATABASE_URL=postgresql+asyncpg://user:password@host:5432/memento \
#     -e DASHSCOPE_API_KEY=sk-xxx \
#     -e JWT_SECRET_KEY=your-secret \
#     -e OSS_ACCESS_KEY_ID=xxx \
#     -e OSS_ACCESS_KEY_SECRET=xxx \
#     memento-cloud:latest
#
# 或使用 docker-compose:
#   docker-compose up -d

FROM python:3.11-slim

LABEL maintainer="Memento-X Team"
LABEL description="Memento-X Cloud Hub — AI intent understanding + task scheduling + account system"

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖（分层缓存）
COPY cloud/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir httpx

# 应用代码
COPY cloud/ cloud/
COPY schema/ schema/

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# 启动命令
CMD ["uvicorn", "cloud.main:app", "--host", "0.0.0.0", "--port", "8000"]