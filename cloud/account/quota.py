"""
Memento-X 用量配额管理

免费用户：每日 10 次意图理解
Pro 用户：每日 200 次意图理解

数据持久化到 PostgreSQL quotas 表，重启不丢失。
"""
import logging
from datetime import date
from cloud.config import settings

logger = logging.getLogger(__name__)


class QuotaManager:
    """配额管理器（PostgreSQL 持久化）"""

    async def get_remaining(self, user_id: str, tier: str = "free") -> int:
        """获取用户今日剩余配额"""
        from cloud.db.engine import async_session_factory
        from cloud.db.crud import quota_get_today

        async with async_session_factory() as db:
            quota = await quota_get_today(db, user_id)
            usage = quota.count
            limit = settings.pro_daily_quota if tier == "pro" else settings.free_daily_quota
            return max(0, limit - usage)

    async def check(self, user_id: str, tier: str = "free") -> bool:
        """检查用户是否还有配额"""
        remaining = await self.get_remaining(user_id, tier)
        return remaining > 0

    async def consume(self, user_id: str) -> bool:
        """消耗一次配额，返回是否成功"""
        from cloud.db.engine import async_session_factory
        from cloud.db.crud import quota_increment

        async with async_session_factory() as db:
            await quota_increment(db, user_id)
            return True

    async def get_usage_today(self, user_id: str) -> int:
        """获取用户今日已使用次数"""
        from cloud.db.engine import async_session_factory
        from cloud.db.crud import quota_get_today

        async with async_session_factory() as db:
            quota = await quota_get_today(db, user_id)
            return quota.count


# 全局配额管理器
_quota_manager = QuotaManager()


async def check_quota(user_id: str) -> bool:
    return await _quota_manager.check(user_id)


async def consume_quota(user_id: str) -> bool:
    return await _quota_manager.consume(user_id)