"""
Memento-X 账号系统 — 用户认证

JWT token 签发与验证，用户注册/登录。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Depends, Header
from cloud.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


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


# ── 用户注册/登录（简化版，生产环境需接入数据库） ──

# 临时内存存储（生产环境替换为 PostgreSQL）
_users: dict = {}
_passwords: dict = {}


async def register_user(email: str, password: str) -> Optional[str]:
    """注册新用户，返回 user_id"""
    if email in _users:
        return None
    user_id = f"user_{len(_users) + 1}"
    _users[email] = user_id
    _passwords[user_id] = hash_password(password)
    return user_id


async def authenticate_user(email: str, password: str) -> Optional[str]:
    """验证用户凭据，返回 user_id"""
    user_id = _users.get(email)
    if not user_id:
        return None
    if not verify_password(password, _passwords.get(user_id, "")):
        return None
    return user_id