"""
Memento-X 本地 API 路由

端点：
- POST /execute      接收工作流 JSON → 执行 → 返回 task_id
- GET  /status/{task_id}  查询任务状态
- GET  /result/{task_id}  获取任务结果
- DELETE /cancel/{task_id} 取消任务
- GET  /health             健康检查
"""
import asyncio
import logging
import uuid
import threading
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request

from local.scheduler import WorkflowExecutor, ExecutionStatus, StepExecutionResult
from local.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 任务存储（内存） ──
# 生产环境应替换为持久化存储
_tasks: Dict[str, dict] = {}
_tasks_lock = threading.Lock()

# ── 执行器（由 server.py 注入） ──
_executor: Optional[WorkflowExecutor] = None


def set_executor(executor: WorkflowExecutor):
    """注入调度器实例"""
    global _executor
    _executor = executor

    # 注册状态回调 → WebSocket 推送
    executor.on_step_update(_on_step_update)


def _push_status(task_id: str, data: dict):
    """从同步线程中安全调用 async WebSocket 推送"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(ws_manager.push_status(task_id, data))
        else:
            asyncio.run(ws_manager.push_status(task_id, data))
    except RuntimeError:
        asyncio.run(ws_manager.push_status(task_id, data))


def _on_step_update(step_result: StepExecutionResult):
    """步骤状态更新回调 → 推送到 WebSocket"""
    task_id = getattr(step_result, 'task_id', None)
    if task_id:
        with _tasks_lock:
            if task_id in _tasks:
                _tasks[task_id]["current_step"] = step_result.step_id
                _tasks[task_id]["step_status"] = step_result.status.value

        _push_status(task_id, {
            "task_id": task_id,
            "step_id": step_result.step_id,
            "status": step_result.status.value,
            "output": step_result.output,
            "error": step_result.error,
            "duration_ms": step_result.duration_ms,
        })


def _run_workflow(task_id: str, workflow: dict, step_result_bridge: dict):
    """后台执行工作流"""
    try:
        with _tasks_lock:
            _tasks[task_id]["status"] = "running"

        _push_status(task_id, {
            "task_id": task_id,
            "status": "running",
            "message": "工作流开始执行",
        })

        # 将 task_id 注入到每个步骤结果中（通过闭包）
        # 在 executor 回调中设置 task_id
        original_notify = _executor._on_step_update

        def _notify_with_task_id(sr):
            sr.task_id = task_id
            if original_notify:
                original_notify(sr)

        _executor._on_step_update = _notify_with_task_id

        result = _executor.execute(workflow)

        # 恢复原始回调
        _executor._on_step_update = original_notify

        with _tasks_lock:
            _tasks[task_id]["status"] = result["status"]
            _tasks[task_id]["result"] = result

        _push_status(task_id, {
            "task_id": task_id,
            "status": result["status"],
            "message": f"工作流执行完成: {result['status']}",
            "result": result,
        })

    except Exception as e:
        logger.exception(f"任务 {task_id} 执行失败")
        with _tasks_lock:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(e)

        _push_status(task_id, {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
        })


# ── 路由 ──

@router.post("/execute")
async def execute_workflow(request: Request):
    """
    接收工作流 JSON，异步执行。

    Request Body:
        {
            "workflow": {...},   // 工作流 JSON
            "task_id": "xxx",    // 可选，云端分配的 task_id
        }

    Response:
        {
            "task_id": "task_xxx",
            "status": "accepted",
            "message": "工作流已接收，开始执行"
        }
    """
    if not _executor:
        raise HTTPException(status_code=503, detail="调度器未初始化")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")

    workflow = body.get("workflow")
    if not workflow:
        raise HTTPException(status_code=400, detail="缺少 workflow 字段")

    if not workflow.get("steps"):
        raise HTTPException(status_code=400, detail="工作流为空（无 steps）")

    # 生成或使用传入的 task_id
    task_id = body.get("task_id") or f"task_{uuid.uuid4().hex[:12]}"

    with _tasks_lock:
        if task_id in _tasks and _tasks[task_id]["status"] == "running":
            raise HTTPException(status_code=409, detail=f"任务 {task_id} 已在执行中")

        _tasks[task_id] = {
            "task_id": task_id,
            "status": "accepted",
            "workflow": workflow,
            "result": None,
            "error": None,
            "current_step": None,
            "step_status": None,
        }

    # 后台线程执行
    thread = threading.Thread(
        target=_run_workflow,
        args=(task_id, workflow, {}),
        daemon=True,
    )
    thread.start()

    logger.info(f"任务已接收: {task_id} ({len(workflow.get('steps', []))} 步)")

    return {
        "task_id": task_id,
        "status": "accepted",
        "message": "工作流已接收，开始执行",
    }


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """
    查询任务执行状态。

    Response:
        {
            "task_id": "task_xxx",
            "status": "running",
            "current_step": "step_2",
            "step_status": "completed"
        }
    """
    with _tasks_lock:
        task = _tasks.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    return {
        "task_id": task_id,
        "status": task["status"],
        "current_step": task.get("current_step"),
        "step_status": task.get("step_status"),
        "error": task.get("error"),
    }


@router.get("/result/{task_id}")
async def get_task_result(task_id: str):
    """
    获取任务执行结果。

    Response:
        {
            "task_id": "task_xxx",
            "status": "success",
            "result": {
                "status": "success",
                "results": {"step_1": "/path/to/output"},
                "errors": {},
                "steps": [...],
                "total_duration_ms": 1234
            }
        }
    """
    with _tasks_lock:
        task = _tasks.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    if task["status"] in ("accepted", "running"):
        return {
            "task_id": task_id,
            "status": task["status"],
            "message": "任务仍在执行中，请稍后查询",
            "result": None,
        }

    return {
        "task_id": task_id,
        "status": task["status"],
        "result": task.get("result"),
        "error": task.get("error"),
    }


@router.delete("/cancel/{task_id}")
async def cancel_task(task_id: str):
    """
    取消正在执行的任务。

    注意：当前实现仅标记取消，不强制中断正在执行的步骤。
    """
    with _tasks_lock:
        task = _tasks.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    if task["status"] not in ("accepted", "running"):
        raise HTTPException(status_code=400, detail=f"任务无法取消（当前状态: {task['status']}）")

    with _tasks_lock:
        _tasks[task_id]["status"] = "cancelled"
        _tasks[task_id]["error"] = "用户取消"

    _push_status(task_id, {
        "task_id": task_id,
        "status": "cancelled",
        "message": "任务已取消",
    })

    return {
        "task_id": task_id,
        "status": "cancelled",
        "message": "任务已取消",
    }


@router.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "service": "Memento-X Local API",
        "version": "0.1.0",
        "executor": "ready" if _executor else "not_initialized",
        "active_tasks": len([t for t in _tasks.values() if t["status"] in ("accepted", "running")]),
    }