"""Memento-X 云端配置"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 通义千问
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")

    # 数据库
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:password@localhost:5432/memento",
    )

    # JWT
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # 服务
    host: str = "0.0.0.0"
    port: int = 8000

    # 配额
    free_daily_quota: int = 10       # 免费用户每日次数
    pro_daily_quota: int = 200       # Pro 用户每日次数

    model_config = {"env_file": ".env"}


settings = Settings()