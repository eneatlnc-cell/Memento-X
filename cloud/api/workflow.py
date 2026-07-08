"""
Memento-X 云端工作流下发 API

端点：
- POST /api/v1/workflow/dispatch  下发工作流到本地
- GET  /api/v1/workflow/status/{task_id}  查询任务状态
- GET  /api/v1/workflow/result/{task_id}  获取任务结果
- GET  /api/v1/workflow/tasks      列出用户任务
- POST /api/v1/local/register      注册本地服务
- POST /api/v1/local/unregister    注销本地服务
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Request

from cloud.models.workflow_task import (
    DispatchRequest,
    DispatchResponse,
    TaskStatus,
)
from cloud.services.dispatch import dispatch_service, DispatchError

# 尝试导入认证依赖（可选）
try:
    from cloud.account.auth import get_current_user
except ImportError:
    # 认证模块不可用时的 fallback
    async def get_current_user(authorization: str = ""):
        return "anonymous"

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 工作流下发 ──

@router.post("/dispatch", response_model=DispatchResponse)
async def dispatch_workflow(
    request: DispatchRequest,
    user_id: str = Depends(get_current_user),
):
    """
    核心 API：将用户指令下发到本地执行。

    完整链路：
    用户输入 → IntentEngine → 工作流JSON → HTTP POST → 本地服务 → 执行
    """
    try:
        response = dispatch_service.dispatch(
            user_input=request.user_input,
            user_id=user_id,
            local_url=request.local_url,
            project_id=request.project_id,
            assets=request.assets,
            context=request.context,
        )
        return response

    except DispatchError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("下发工作流失败")
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


# ── 任务状态查询 ──

@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    user_id: str = Depends(get_current_user),
):
    """
    查询任务状态（从云端缓存或本地拉取）。
    """
    status = dispatch_service.get_task_status(task_id)
    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return status


@router.get("/result/{task_id}")
async def get_task_result(
    task_id: str,
    user_id: str = Depends(get_current_user),
):
    """
    获取任务执行结果。
    """
    result = dispatch_service.get_task_result(task_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return result


@router.get("/tasks")
async def list_tasks(
    user_id: str = Depends(get_current_user),
    limit: int = 20,
):
    """
    列出用户的历史任务。
    """
    tasks = dispatch_service.list_user_tasks(user_id, limit=limit)
    return {"tasks": tasks, "total": len(tasks)}


# ── 本地服务注册 ──

@router.post("/local/register")
async def register_local(request: Request):
    """
    注册用户的本地服务地址。

    Request Body:
        {
            "host": "192.168.1.100",
            "port": 8000
        }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")

    host = body.get("host")
    port = body.get("port", 8000)

    if not host:
        raise HTTPException(status_code=400, detail="缺少 host 字段")

    # 使用 host 作为简易 user_id（生产环境应使用 JWT 中的 user_id）
    user_id = body.get("user_id", host)

    dispatch_service.register_local(user_id, host, port)
    return {"status": "registered", "user_id": user_id, "url": f"http://{host}:{port}"}


@router.post("/local/unregister")
async def unregister_local(request: Request):
    """
    注销用户的本地服务。
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")

    user_id = body.get("user_id", body.get("host", "unknown"))
    dispatch_service.unregister_local(user_id)
    return {"status": "unregistered", "user_id": user_id}