"""
Memento-X 云端下发服务

负责将意图理解引擎生成的工作流 JSON 下发到用户本地的 API 服务。

核心流程：
1. 调用 IntentEngine.process() 生成工作流 JSON
2. 通过 HTTP POST 将工作流 JSON 发送到用户本机
3. 接收本地服务的执行结果
4. 支持查询执行进度
"""
import logging
from datetime import datetime
from typing import Optional, List

import requests

from cloud.intent.engine import engine
from cloud.models.workflow_task import (
    WorkflowTask,
    TaskStatus,
    TaskPriority,
    DispatchRequest,
    DispatchResponse,
)

logger = logging.getLogger(__name__)

# 超时配置
DISPATCH_TIMEOUT = 300  # 下发超时（秒）
STATUS_POLL_INTERVAL = 2  # 状态轮询间隔（秒）


class DispatchError(Exception):
    """下发失败"""
    def __init__(self, task_id: str, reason: str):
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"下发失败 [{task_id}]: {reason}")


class DispatchService:
    """
    下发服务。

    使用方式：
        service = DispatchService()
        response = service.dispatch(
            user_input="把人物换成钢铁侠",
            user_id="user_001",
            local_url="http://192.168.1.100:8000",
            assets=[{"id": "asset_047", "name": "人物"}],
        )
    """

    def __init__(self):
        self._tasks: dict[str, WorkflowTask] = {}

    # ── 公共 API ──

    def create_task(
        self,
        user_input: str,
        user_id: str = "anonymous",
        local_url: Optional[str] = None,
        project_id: Optional[str] = None,
        assets: Optional[List[dict]] = None,
        context: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> WorkflowTask:
        """
        创建任务（不执行，仅创建 WorkflowTask 实例）。

        Args:
            user_input: 用户自然语言输入
            user_id: 用户 ID
            local_url: 用户本机 API 地址
            project_id: 项目 ID
            assets: 素材库引用列表
            context: 额外上下文
            priority: 任务优先级

        Returns:
            WorkflowTask: 新创建的任务
        """
        task = WorkflowTask(
            user_id=user_id,
            user_input=user_input,
            project_id=project_id,
            assets=assets,
            local_url=local_url,
            priority=priority,
            status=TaskStatus.CREATED,
        )
        self._tasks[task.task_id] = task
        logger.info(f"任务已创建: {task.task_id} (priority={priority.name})")
        return task

    def dispatch(
        self,
        user_input: str,
        user_id: str = "anonymous",
        local_url: Optional[str] = None,
        project_id: Optional[str] = None,
        assets: Optional[List[dict]] = None,
        context: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> DispatchResponse:
        """
        下发工作流到本地执行（同步模式，直接下发不入队）。

        完整链路：
        user_input → IntentEngine.process() → 工作流JSON → HTTP POST → 本地执行

        Args:
            user_input: 用户自然语言输入
            user_id: 用户 ID
            local_url: 用户本机 API 地址（如未提供，从注册表中查找）
            project_id: 项目 ID
            assets: 素材库引用列表
            context: 额外上下文
            priority: 任务优先级

        Returns:
            DispatchResponse: 下发结果

        Raises:
            DispatchError: 下发失败
        """
        # 1. 创建任务
        task = self.create_task(
            user_input=user_input,
            user_id=user_id,
            local_url=local_url,
            project_id=project_id,
            assets=assets,
            context=context,
            priority=priority,
        )

        # 2. 解析本地服务地址
        if not task.local_url:
            from cloud.services.scheduler import task_scheduler
            task.local_url = task_scheduler.get_local_url(user_id)
            if not task.local_url:
                task.status = TaskStatus.FAILED
                task.error = "用户未注册本地服务地址"
                raise DispatchError(task.task_id, task.error)

        # 3. 调用意图理解引擎
        try:
            logger.info(f"意图理解: {user_input[:50]}...")
            workflow = engine.process(
                user_input=user_input,
                assets=assets,
                context=context,
                project_id=project_id,
            )
            task.workflow = workflow
            logger.info(f"工作流生成: {len(workflow.get('steps', []))} 步")
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = f"意图理解失败: {str(e)}"
            raise DispatchError(task.task_id, task.error)

        # 4. 下发到本地
        try:
            task.status = TaskStatus.DISPATCHED
            task.dispatched_at = datetime.utcnow()

            result = self._send_to_local(task.local_url, task.task_id, workflow)
            logger.info(f"本地已接收: {task.task_id}")

        except requests.exceptions.ConnectionError:
            task.status = TaskStatus.FAILED
            task.error = f"无法连接到本地服务: {task.local_url}"
            raise DispatchError(task.task_id, task.error)
        except requests.exceptions.Timeout:
            task.status = TaskStatus.TIMEOUT
            task.error = f"下发超时: {task.local_url}"
            raise DispatchError(task.task_id, task.error)
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = f"下发失败: {str(e)}"
            raise DispatchError(task.task_id, task.error)

        # 5. 生成预览
        workflow_preview = self._build_preview(workflow)

        # 6. 推送状态（异步）
        self._notify_status(task)

        return DispatchResponse(
            task_id=task.task_id,
            status="dispatched",
            local_url=task.local_url,
            message=f"工作流已下发到本地（{len(workflow.get('steps', []))} 步）",
            workflow_preview=workflow_preview,
        )

    def get_task(self, task_id: str) -> Optional[WorkflowTask]:
        """获取任务"""
        return self._tasks.get(task_id)

    def get_task_status(self, task_id: str) -> dict:
        """
        获取任务状态（从本地服务拉取最新状态）。

        Args:
            task_id: 任务 ID

        Returns:
            dict: 任务状态
        """
        task = self._tasks.get(task_id)
        if not task:
            return {"task_id": task_id, "status": "not_found"}

        # 如果任务正在执行，从本地拉取最新状态
        if task.status in (TaskStatus.DISPATCHED, TaskStatus.ACCEPTED, TaskStatus.RUNNING):
            try:
                local_status = self._poll_local_status(task.local_url, task_id)
                if local_status:
                    task.status = TaskStatus(local_status.get("status", task.status))
                    task.current_step = local_status.get("current_step")
                    task.step_status = local_status.get("step_status")

                    if task.status == TaskStatus.COMPLETED:
                        result = self._fetch_local_result(task.local_url, task_id)
                        if result:
                            task.result = result.get("result")
                            task.completed_at = datetime.utcnow()
            except Exception:
                pass  # 拉取失败不影响返回

        return {
            "task_id": task.task_id,
            "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
            "user_input": task.user_input[:100],
            "current_step": task.current_step,
            "step_status": task.step_status,
            "progress": task.progress,
            "retry_count": task.retry_count,
            "error": task.error,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    def get_task_result(self, task_id: str) -> dict:
        """
        获取任务结果。

        Args:
            task_id: 任务 ID

        Returns:
            dict: 任务结果
        """
        task = self._tasks.get(task_id)
        if not task:
            return {"task_id": task_id, "status": "not_found"}

        # 如果本地有结果，尝试拉取
        if task.status != TaskStatus.COMPLETED and task.local_url:
            try:
                result = self._fetch_local_result(task.local_url, task_id)
                if result and result.get("result"):
                    task.result = result["result"]
                    task.status = TaskStatus(result.get("status", "completed"))
                    task.completed_at = datetime.utcnow()
            except Exception:
                pass

        return {
            "task_id": task.task_id,
            "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
            "result": task.result,
            "error": task.error,
            "retry_count": task.retry_count,
        }

    def update_task_status(self, task_id: str, status: TaskStatus, **kwargs):
        """更新任务状态并推送通知"""
        task = self._tasks.get(task_id)
        if not task:
            return
        task.status = status
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        self._notify_status(task)

    def list_user_tasks(self, user_id: str, limit: int = 20) -> List[dict]:
        """列出用户的任务"""
        user_tasks = [
            t for t in self._tasks.values()
            if t.user_id == user_id
        ]
        user_tasks.sort(key=lambda t: t.created_at or datetime.min, reverse=True)
        return [
            {
                "task_id": t.task_id,
                "status": t.status.value if isinstance(t.status, TaskStatus) else t.status,
                "priority": t.priority.name if isinstance(t.priority, TaskPriority) else "NORMAL",
                "user_input": t.user_input[:80],
                "retry_count": t.retry_count,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in user_tasks[:limit]
        ]

    # ── 内部方法 ──

    def _send_to_local(self, local_url: str, task_id: str, workflow: dict) -> dict:
        """
        通过 HTTP POST 将工作流发送到本地服务。

        Args:
            local_url: 本地 API 地址
            task_id: 任务 ID
            workflow: 工作流 JSON

        Returns:
            dict: 本地服务响应
        """
        url = f"{local_url.rstrip('/')}/api/v1/local/execute"
        payload = {
            "task_id": task_id,
            "workflow": workflow,
        }

        response = requests.post(
            url,
            json=payload,
            timeout=DISPATCH_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def _poll_local_status(self, local_url: str, task_id: str) -> Optional[dict]:
        """
        从本地服务拉取任务状态。

        Args:
            local_url: 本地 API 地址
            task_id: 任务 ID

        Returns:
            dict | None: 状态数据
        """
        try:
            url = f"{local_url.rstrip('/')}/api/v1/local/status/{task_id}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def _fetch_local_result(self, local_url: str, task_id: str) -> Optional[dict]:
        """
        从本地服务拉取任务结果。

        Args:
            local_url: 本地 API 地址
            task_id: 任务 ID

        Returns:
            dict | None: 结果数据
        """
        try:
            url = f"{local_url.rstrip('/')}/api/v1/local/result/{task_id}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def _build_preview(self, workflow: dict) -> dict:
        """构建工作流预览"""
        steps = workflow.get("steps", [])
        return {
            "understood": workflow.get("understood", ""),
            "total_steps": len(steps),
            "steps": [
                {
                    "id": s.get("id", f"step_{i}"),
                    "action": s.get("action", ""),
                    "depends_on": s.get("depends_on", []),
                }
                for i, s in enumerate(steps)
            ],
        }

    def _notify_status(self, task: WorkflowTask):
        """异步推送任务状态变更（fire-and-forget）"""
        try:
            from cloud.services.push import push_service
            import asyncio
            asyncio.ensure_future(
                push_service.push_status(task.user_id, {
                    "task_id": task.task_id,
                    "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
                    "progress": task.progress,
                    "retry_count": task.retry_count,
                    "error": task.error,
                })
            )
        except Exception:
            pass  # 推送失败不影响主流程


# ── 全局单例 ──
dispatch_service = DispatchService()