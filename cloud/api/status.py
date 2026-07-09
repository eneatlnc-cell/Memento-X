"""
Memento-X 云端状态 API

端点：
- WS   /api/v1/status/ws          WebSocket 实时状态推送
- POST /api/v1/status/report      本地引擎状态上报
- GET  /api/v1/status/connections  WebSocket 连接数
- GET  /api/v1/status/local       本地引擎注册列表
"""
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request

from cloud.services.push import push_service
from cloud.services.dispatch import dispatch_service
from cloud.services.scheduler import task_scheduler
from cloud.models.workflow_task import StatusReport

logger = logging.getLogger(__name__)

router = APIRouter()


# ── WebSocket ──

@router.websocket("/ws")
async def websocket_status(websocket: WebSocket, token: str = ""):
    """
    WebSocket 实时状态推送。

    连接参数: ?token=<user_id>
    协议:
        client → server: "ping" → server 回复 "pong"
        server → client: JSON 消息（任务状态变更、本地引擎状态变更）
    """
    user_id = token or "anonymous"
    await push_service.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await push_service.handle_ping(websocket, user_id)
            elif data.startswith("{"):
                # JSON 消息（预留扩展）
                pass
            else:
                await websocket.send_text(f"unknown: {data}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket 客户端断开: user={user_id}")
    except Exception:
        logger.exception(f"WebSocket 异常: user={user_id}")
    finally:
        push_service.disconnect(websocket, user_id)


# ── 状态上报 ──

@router.post("/report")
async def report_status(request: Request):
    """
    本地引擎上报任务状态。

    请求体: StatusReport
    请求来源: 本地 Memento-X local 引擎
    """
    body = await request.json()
    report = StatusReport(**body)

    # 更新任务状态
    from cloud.models.workflow_task import TaskStatus
    try:
        status = TaskStatus(report.status)
    except ValueError:
        status = TaskStatus.RUNNING

    dispatch_service.update_task_status(
        report.task_id,
        status,
        current_step=report.step_id,
        step_status=report.step_status,
        progress=report.progress,
        error=report.error,
        result=report.result,
    )

    logger.info(f"状态上报: {report.task_id} → {report.status} (progress={report.progress})")
    return {"status": "ok", "task_id": report.task_id}


# ── 查询 ──

@router.get("/connections")
async def get_connection_count():
    """获取 WebSocket 连接数"""
    return {
        "total": push_service.get_connection_count(),
    }


@router.get("/local")
async def get_local_registrations():
    """获取所有本地引擎注册列表"""
    regs = task_scheduler.get_all_registrations()
    return {
        "total": len(regs),
        "registrations": [
            {
                "user_id": r.user_id,
                "host": r.host,
                "port": r.port,
                "version": r.version,
                "status": r.status,
                "last_heartbeat": r.last_heartbeat.isoformat(),
                "registered_at": r.registered_at.isoformat(),
            }
            for r in regs.values()
        ],
    }