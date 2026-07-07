"""Memento-X 云端入口 — FastAPI 服务"""
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cloud.config import settings
from cloud.api.intent import router as intent_router
from cloud.api.account import router as account_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title="Memento-X Cloud",
    description="AI 意图理解 + 账号系统 — AI 只做意图理解，像素级工作全部由本地确定性工具完成",
    version="0.1.0",
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Memento-X Cloud", "version": "0.1.0"}


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)