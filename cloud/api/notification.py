"""
Memento-X 云端通知 API

端点：
- POST /api/v1/notification/register  注册 FCM Token
- POST /api/v1/notification/push      推送通知到手机端
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 内存存储（生产环境接入 PostgreSQL）──
_fcm_tokens: dict[str, list[str]] = {}  # user_id → [fcm_token, ...]


# ── 请求模型 ──

class FcmRegisterRequest(BaseModel):
    """FCM Token 注册请求"""
    fcm_token: str = Field(..., description="Firebase Cloud Messaging Token")


class PushRequest(BaseModel):
    """推送通知请求"""
    user_id: str = Field(..., description="目标用户 ID")
    task_id: Optional[str] = Field(None, description="关联任务 ID")
    title: str = Field(..., description="通知标题")
    body: str = Field(default="", description="通知正文")
    data: Optional[dict] = Field(None, description="附加数据（task_id, status, video_url 等）")


# ── 端点 ──

@router.post("/register")
async def register_fcm_token(req: FcmRegisterRequest):
    """
    注册 FCM Token。

    手机端在获取 FCM Token 后调用此端点，将 token 与用户关联。
    用于后续任务完成时推送通知。
    """
    # 从请求上下文获取 user_id（生产环境通过 JWT 解析）
    # 当前简化实现：token 作为唯一标识
    logger.info(f"FCM Token 已注册: {req.fcm_token[:20]}...")
    return {"registered": True}


@router.post("/push")
async def push_notification(req: PushRequest):
    """
    推送通知到手机端。

    云端在任务完成时调用此端点，通过 FCM 向手机端推送通知。
    通知内容包含 task_id、status、video_url 等关键信息。

    当前为占位实现，生产环境接入 Firebase Admin SDK。
    """
    logger.info(f"推送通知: user={req.user_id}, title={req.title}, task={req.task_id}")
    return {
        "sent": True,
        "user_id": req.user_id,
        "task_id": req.task_id,
        "message": "通知已推送（占位实现，生产环境接入 Firebase Admin SDK）",
    }