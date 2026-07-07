"""云端账号系统模型"""
from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional


class User(BaseModel):
    id: str
    email: EmailStr
    tier: str = "free"  # free / pro / enterprise
    created_at: datetime
    updated_at: Optional[datetime] = None


class Subscription(BaseModel):
    user_id: str
    tier: str
    started_at: datetime
    expires_at: Optional[datetime] = None
    auto_renew: bool = False