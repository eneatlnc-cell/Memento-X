"""
Memento-X 账号系统 — 用户认证

JWT token 签发与验证，用户注册/登录。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import HTTPException, Depends, Header
from cloud.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """签发 JWT access token"""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    payload = {"sub": user_id, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[str]:
    """验证并解码 JWT token，返回 user_id"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


async def get_current_user(authorization: str = Header(...)) -> str:
    """FastAPI 依赖注入：从 Authorization header 提取当前用户"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[7:]
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_id


# ── 用户注册/登录（PostgreSQL 持久化）──


async def register_user(email: str, password: str) -> Optional[str]:
    """
    注册新用户，返回 user_id。

    使用数据库持久化，重启不丢失数据。
    """
    from cloud.db.engine import async_session_factory
    from cloud.db.crud import user_create

    async with async_session_factory() as db:
        user = await user_create(db, email, hash_password(password))
        if user is None:
            return None
        return user.id


async def authenticate_user(email: str, password: str) -> Optional[str]:
    """
    验证用户凭据，返回 user_id。

    从数据库查询用户并验证密码哈希。
    """
    from cloud.db.engine import async_session_factory
    from cloud.db.crud import user_get_by_email

    async with async_session_factory() as db:
        user = await user_get_by_email(db, email)
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user.id