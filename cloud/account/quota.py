"""
Memento-X 用量配额管理

免费用户：每日 10 次意图理解
Pro 用户：每日 200 次意图理解
"""
from datetime import datetime, date
from cloud.config import settings


class QuotaManager:
    """配额管理器（简化版，生产环境需接入 Redis/PostgreSQL）"""

    def __init__(self):
        self._daily_usage: dict[str, dict[str, int]] = {}  # user_id -> {date_str -> count}

    async def get_remaining(self, user_id: str, tier: str = "free") -> int:
        """获取用户今日剩余配额"""
        today = str(date.today())
        usage = self._daily_usage.get(user_id, {}).get(today, 0)
        limit = settings.pro_daily_quota if tier == "pro" else settings.free_daily_quota
        return max(0, limit - usage)

    async def check(self, user_id: str, tier: str = "free") -> bool:
        """检查用户是否还有配额"""
        remaining = await self.get_remaining(user_id, tier)
        return remaining > 0

    async def consume(self, user_id: str) -> bool:
        """消耗一次配额，返回是否成功"""
        today = str(date.today())
        if user_id not in self._daily_usage:
            self._daily_usage[user_id] = {}
        self._daily_usage[user_id][today] = self._daily_usage[user_id].get(today, 0) + 1
        return True

    async def get_usage_today(self, user_id: str) -> int:
        """获取用户今日已使用次数"""
        today = str(date.today())
        return self._daily_usage.get(user_id, {}).get(today, 0)


# 全局配额管理器
_quota_manager = QuotaManager()


async def check_quota(user_id: str) -> bool:
    return await _quota_manager.check(user_id)


async def consume_quota(user_id: str) -> bool:
    return await _quota_manager.consume(user_id)