"""
Memento-X 异步数据库引擎

基于 SQLAlchemy 2.0 async + asyncpg 连接 PostgreSQL。
"""
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from cloud.config import settings

logger = logging.getLogger(__name__)

# ── 异步引擎 ──
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,          # 连接前检测可用性
    pool_recycle=3600,           # 1 小时回收连接
)

# ── 会话工厂 ──
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── ORM 基类 ──
class Base(DeclarativeBase):
    pass


# ── 依赖注入 ──
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入：每个请求获取一个独立的数据库会话"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


# ── 初始化 ──
async def init_db():
    """
    创建所有未存在的表（开发环境用，生产环境应使用 Alembic 迁移）。
    """
    from cloud.db.models import all_models  # noqa: F401 确保所有模型被导入
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表已创建/验证完成")