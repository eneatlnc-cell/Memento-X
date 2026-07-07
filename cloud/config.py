"""Memento-X 云端配置"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings

# 项目根目录（从 cloud/config.py 向上两级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # ── 通义千问 ──
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")

    # ── 意图理解引擎 ──
    intent_model: str = os.getenv("INTENT_MODEL", "qwen-vl-pro")
    intent_temperature: float = float(os.getenv("INTENT_TEMPERATURE", "0.1"))
    intent_max_tokens: int = int(os.getenv("INTENT_MAX_TOKENS", "3000"))
    intent_max_retries: int = int(os.getenv("INTENT_MAX_RETRIES", "2"))

    # ── Schema ──
    schema_path: str = os.getenv(
        "SCHEMA_PATH",
        str(PROJECT_ROOT / "schema" / "workflow.json"),
    )

    # ── 数据库 ──
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:password@localhost:5432/memento",
    )

    # ── JWT ──
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # ── 服务 ──
    host: str = "0.0.0.0"
    port: int = 8000

    # ── 配额 ──
    free_daily_quota: int = 10
    pro_daily_quota: int = 200

    model_config = {"env_file": ".env"}


settings = Settings()