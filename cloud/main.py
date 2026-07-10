"""Memento-X 云端入口 — FastAPI 服务"""
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cloud.config import settings
from cloud.api.intent import router as intent_router
from cloud.api.account import router as account_router
from cloud.api.workflow import router as workflow_router
from cloud.api.status import router as status_router
from cloud.api.asset import router as asset_router
from cloud.api.notification import router as notification_router
from cloud.api.dataset import router as dataset_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# ── 生命周期管理 ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期。

    startup: 启动调度器、PushService 后台任务，绑定依赖
    shutdown: 优雅停止所有后台任务
    """
    # ── startup ──
    from cloud.services.scheduler import task_scheduler
    from cloud.services.push import push_service
    from cloud.services.dispatch import dispatch_service
    from cloud.db.engine import init_db

    # 数据库初始化（自动建表）
    try:
        await init_db()
        logger.info("数据库连接成功，表已就绪")
    except Exception as e:
        logger.warning(f"数据库初始化跳过（未配置 PostgreSQL）: {e}")

    # 绑定依赖：调度器 ← 推送服务
    task_scheduler.bind_push(push_service.push_status)

    # 启动后台任务
    await task_scheduler.start()
    await push_service.start()

    logger.info("Memento-X Cloud v0.3.0 已启动")
    logger.info(f"  端点: http://{settings.host}:{settings.port}")
    logger.info(f"  调度器: 队列 worker + 心跳监控 (30s) + 主动轮询")
    logger.info(f"  PushService: 连接清理循环 (30s ping, 90s ttl)")
    logger.info(f"  数据库: PostgreSQL (asyncpg)")

    yield

    # ── shutdown ──
    logger.info("正在关闭 Memento-X Cloud...")
    await task_scheduler.stop()
    await push_service.stop()
    logger.info("Memento-X Cloud 已关闭")


app = FastAPI(
    title="Memento-X Cloud",
    description="AI 意图理解 + 任务调度 + 账号系统 — AI 只做意图理解，像素级工作全部由本地确定性工具完成",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(intent_router, prefix="/api/v1/intent", tags=["intent"])
app.include_router(account_router, prefix="/api/v1/account", tags=["account"])
app.include_router(workflow_router, prefix="/api/v1/workflow", tags=["workflow"])
app.include_router(status_router, prefix="/api/v1/status", tags=["status"])
app.include_router(asset_router, prefix="/api/v1/asset", tags=["asset"])
app.include_router(notification_router, prefix="/api/v1/notification", tags=["notification"])
app.include_router(dataset_router, prefix="/api/v1/dataset", tags=["dataset"])


@app.get("/health")
async def health():
    from cloud.services.scheduler import task_scheduler
    from cloud.services.push import push_service
    return {
        "status": "ok",
        "service": "Memento-X Cloud",
        "version": "0.2.0",
        "queue_size": task_scheduler.get_queue_size(),
        "ws_connections": push_service.get_connection_count(),
    }


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)