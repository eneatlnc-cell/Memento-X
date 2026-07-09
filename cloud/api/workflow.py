"""
Memento-X 云端工作流 API

端点：
- POST /api/v1/workflow/generate   生成工作流 JSON
- POST /api/v1/workflow/dispatch   下发工作流到本地执行
- GET  /api/v1/workflow/status/{id} 查询任务状态
- GET  /api/v1/workflow/result/{id} 获取任务结果
- GET  /api/v1/workflow/tasks        列出用户任务
- POST /api/v1/workflow/local/register   本地引擎注册
- POST /api/v1/workflow/local/unregister 本地引擎注销
- POST /api/v1/workflow/local/heartbeat  本地引擎心跳
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request

from cloud.auth import get_current_user
from cloud.services.dispatch import dispatch_service, DispatchError
from cloud.services.scheduler import task_scheduler
from cloud.models.workflow_task import (
    DispatchRequest,
    DispatchResponse,
    HeartbeatRequest,
    TaskPriority,
    TaskStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 工作流生成 ──

@router.post("/generate")
async def generate_workflow(request: DispatchRequest, user_id: str = Depends(get_current_user)):
    """
    生成工作流 JSON（不执行，仅预览）。

    调用意图理解引擎，将用户自然语言输入转换为结构化工作流。
    """
    from cloud.intent.engine import engine

    try:
        workflow = engine.process(
            user_input=request.user_input,
            assets=request.assets,
            context=request.context,
            project_id=request.project_id,
        )
        return {
            "user_id": user_id,
            "workflow": workflow,
            "total_steps": len(workflow.get("steps", [])),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"工作流生成失败: {str(e)}")


# ── 任务下发 ──

@router.post("/dispatch", response_model=DispatchResponse)
async def dispatch_workflow(request: DispatchRequest, user_id: str = Depends(get_current_user)):
    """
    下发工作流到本地执行（通过调度器入队）。

    流程：
    1. 创建任务 → 入队 → 调度器按优先级消费
    2. 意图理解 → 工作流 JSON → HTTP POST → 本地引擎
    3. 失败自动重试（最多 3 次）
    """
    try:
        # 创建任务
        task = dispatch_service.create_task(
            user_input=request.user_input,
            user_id=user_id,
            local_url=request.local_url,
            project_id=request.project_id,
            assets=request.assets,
            context=request.context,
            priority=request.priority,
        )

        # 入队（调度器异步消费）
        queue_position = await task_scheduler.enqueue(task)

        # 生成预览
        from cloud.intent.engine import engine
        try:
            workflow = engine.process(
                user_input=request.user_input,
                assets=request.assets,
                context=request.context,
                project_id=request.project_id,
            )
            task.workflow = workflow
            preview = dispatch_service._build_preview(workflow)
        except Exception:
            preview = None

        return DispatchResponse(
            task_id=task.task_id,
            status="queued",
            local_url=request.local_url or task_scheduler.get_local_url(user_id),
            message=f"任务已入队（优先级 {request.priority.name}）",
            workflow_preview=preview,
            queue_position=queue_position,
        )

    except DispatchError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 任务状态与结果 ──

@router.get("/status/{task_id}")
async def get_task_status(task_id: str, user_id: str = Depends(get_current_user)):
    """查询任务状态"""
    status = dispatch_service.get_task_status(task_id)
    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="任务不存在")
    return status


@router.get("/result/{task_id}")
async def get_task_result(task_id: str, user_id: str = Depends(get_current_user)):
    """获取任务结果"""
    result = dispatch_service.get_task_result(task_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="任务不存在")
    return result


@router.get("/tasks")
async def list_tasks(user_id: str = Depends(get_current_user), limit: int = 20):
    """列出用户任务"""
    return dispatch_service.list_user_tasks(user_id, limit)


# ── 本地引擎管理 ──

@router.post("/local/register")
async def register_local(request: Request):
    """
    注册本地引擎。

    请求体: { "user_id": str, "host": str, "port": int, "version": str }
    """
    body = await request.json()
    user_id = body.get("user_id", "")
    host = body.get("host", "127.0.0.1")
    port = body.get("port", 8000)
    version = body.get("version", "1.0.0")

    if not user_id:
        raise HTTPException(status_code=400, detail="缺少 user_id")

    task_scheduler.register_local(user_id, host, port, version)
    return {
        "status": "ok",
        "user_id": user_id,
        "local_url": f"http://{host}:{port}",
        "message": "本地引擎已注册",
    }


@router.post("/local/unregister")
async def unregister_local(request: Request):
    """
    注销本地引擎。

    请求体: { "user_id": str }
    """
    body = await request.json()
    user_id = body.get("user_id", "")

    if not user_id:
        raise HTTPException(status_code=400, detail="缺少 user_id")

    task_scheduler.unregister_local(user_id)
    return {"status": "ok", "user_id": user_id, "message": "本地引擎已注销"}


@router.post("/local/heartbeat")
async def heartbeat(request: Request):
    """
    本地引擎心跳上报。

    请求体: HeartbeatRequest
    频率: 每 30 秒上报一次
    超时: 连续 90 秒未上报标记为 offline

    返回: { "status": "ok", "is_new": bool, "next_heartbeat_in": 30 }
    """
    body = await request.json()
    hb = HeartbeatRequest(**body)

    is_new = task_scheduler.heartbeat(
        user_id=hb.user_id,
        host=hb.host,
        port=hb.port,
        version=hb.version,
        active_tasks=hb.active_tasks,
        gpu_available=hb.gpu_available,
    )

    return {
        "status": "ok",
        "is_new": is_new,
        "next_heartbeat_in": 30,
        "message": "首次注册" if is_new else "心跳已更新",
    }


@router.get("/local/status/{user_id}")
async def get_local_status(user_id: str):
    """
    查询本地引擎在线状态。

    返回: { "user_id": str, "online": bool, "local_url": str, "last_heartbeat": str, ... }
    """
    reg = task_scheduler.get_registration(user_id)
    if not reg:
        return {"user_id": user_id, "online": False, "message": "未注册"}

    from datetime import datetime
    elapsed = (datetime.utcnow() - reg.last_heartbeat).total_seconds()

    return {
        "user_id": reg.user_id,
        "online": reg.status == "online",
        "status": reg.status,
        "local_url": f"http://{reg.host}:{reg.port}",
        "version": reg.version,
        "last_heartbeat": reg.last_heartbeat.isoformat(),
        "seconds_since_heartbeat": int(elapsed),
        "registered_at": reg.registered_at.isoformat(),
    }


@router.get("/queue/status")
async def get_queue_status():
    """
    查询调度器队列状态。

    返回: { "queue_size": int, "registrations": int, "online_count": int }
    """
    regs = task_scheduler.get_all_registrations()
    online = sum(1 for r in regs.values() if r.status == "online")

    return {
        "queue_size": task_scheduler.get_queue_size(),
        "registrations": len(regs),
        "online_count": online,
    }