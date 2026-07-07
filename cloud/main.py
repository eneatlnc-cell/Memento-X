"""Memento-X 云端入口 — FastAPI 服务"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cloud.config import settings
from cloud.api.intent import router as intent_router
from cloud.api.account import router as account_router

app = FastAPI(
    title="Memento-X Cloud",
    description="AI 意图理解 + 账号系统",
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
    return {"status": "ok", "service": "Memento-X Cloud"}


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)