"""
Memento-X 云端状态查询 API

端点：
- GET  /api/v1/status/ws      WebSocket 状态推送
- POST /api/v1/status/report  接收本地服务上报的状态
"""
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request

from cloud.services.push import push_service
from cloud.services.dispatch import dispatch_service
from cloud.models.workflow_task import StatusReport, TaskStatus
from cloud.account.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ── WebSocket 状态推送 ──

@router.websocket("/ws")
async def websocket_status(
    websocket: WebSocket,
    token: str = "",
):
    """
    云端 WebSocket 状态推送。

    客户端通过此端点订阅任务状态更新。

    连接参数：
        token: JWT 认证令牌（query parameter）
    """
    # 简易认证：从 token 中提取 user_id
    # 生产环境应使用 JWT 验证
    user_id = token or "anonymous"

    await push_service.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        push_service.disconnect(websocket, user_id)
    except Exception:
        push_service.disconnect(websocket, user_id)


# ── 状态上报 ──

@router.post("/report")
async def report_status(
    request: Request,
):
    """
    接收本地服务上报的任务状态。

    本地调度器在每一步执行后，通过此接口向云端回传状态。

    Request Body:
        {
            "task_id": "task_xxx",
            "status": "running",
            "step_id": "step_1",
            "step_status": "completed",
            "progress": 0.25,
            "error": null,
            "result": null
        }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")

    task_id = body.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="缺少 task_id")

    status = body.get("status", "unknown")
    step_id = body.get("step_id")
    step_status = body.get("step_status")
    progress = body.get("progress")
    error = body.get("error")
    result = body.get("result")

    # 更新云端任务状态
    task = dispatch_service.get_task(task_id)
    if task:
        try:
            task.status = TaskStatus(status) if status in TaskStatus.__members__ else task.status
        except (ValueError, KeyError):
            pass
        task.current_step = step_id or task.current_step
        task.step_status = step_status or task.step_status
        task.progress = progress or task.progress
        task.error = error or task.error
        task.result = result or task.result

    # 推送到订阅该用户的客户端
    user_id = task.user_id if task else "anonymous"
    await push_service.push_status(user_id, {
        "task_id": task_id,
        "status": status,
        "step_id": step_id,
        "step_status": step_status,
        "progress": progress,
        "error": error,
    })

    logger.debug(f"状态已接收: {task_id} → {status}")

    return {
        "received": True,
        "task_id": task_id,
        "status": status,
    }


@router.get("/connections")
async def get_connection_count():
    """获取当前 WebSocket 连接数"""
    return {
        "connections": push_service.get_connection_count(),
    }