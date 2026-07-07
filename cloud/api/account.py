"""账号 API 路由"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from cloud.account.auth import register_user, authenticate_user, create_access_token

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    """用户注册"""
    user_id = await register_user(req.email, req.password)
    if user_id is None:
        raise HTTPException(status_code=409, detail="邮箱已注册")

    token = create_access_token(user_id)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """用户登录"""
    user_id = await authenticate_user(req.email, req.password)
    if user_id is None:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_access_token(user_id)
    return TokenResponse(access_token=token)