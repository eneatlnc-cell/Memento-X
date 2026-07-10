"""
Memento-X 云端任务调度器（M10）

核心功能：
- 优先级任务队列（asyncio.PriorityQueue）
- 本地引擎心跳监控（30s 间隔，90s 超时）
- 主动轮询健康检查（超时后 HTTP 探活，确认启动器是否真的挂了）
- 任务失败自动重试（最多 3 次，指数退避）
- 与 PushService 集成，实时推送状态变更

数据持久化：
- 注册表持久化到 PostgreSQL launchers 表
- 重启后自动恢复所有注册信息

生命周期：
    from cloud.services.scheduler import task_scheduler

    # 在 FastAPI startup 事件中启动
    await task_scheduler.start()

    # 在 FastAPI shutdown 事件中停止
    await task_scheduler.stop()
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict

import httpx

from cloud.models.workflow_task import (
    WorkflowTask,
    TaskStatus,
    TaskPriority,
    LocalRegistration,
)

logger = logging.getLogger(__name__)

# ── 配置常量 ──
HEARTBEAT_INTERVAL = 30       # 心跳检查间隔（秒）
HEARTBEAT_TIMEOUT = 90        # 心跳超时阈值（秒），3 倍心跳间隔
ACTIVE_POLL_TIMEOUT = 5       # 主动探活 HTTP 超时（秒）
RETRY_BACKOFF_BASE = 2        # 重试退避基数（秒）：2^0=1s, 2^1=2s, 2^2=4s
MAX_CONCURRENT_TASKS = 1      # 最大并发任务数（本地引擎串行执行）


class TaskScheduler:
    """
    云端任务调度器。

    - 优先级队列：高优先级任务优先出队
    - 心跳监控：后台定时检查本地引擎是否存活
    - 主动轮询：超时后 HTTP GET 探活，避免误判
    - 自动重试：下发失败后指数退避重试
    - 持久化：注册表存储到 PostgreSQL
    """

    def __init__(self):
        # 优先级队列：(priority, timestamp, task)
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()

        # 本地引擎注册表（内存缓存，数据库为权威源）
        self._local_registry: Dict[str, LocalRegistration] = {}

        # 后台任务引用
        self._worker_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

        # 外部依赖（延迟注入，避免循环导入）
        self._dispatch_fn = None
        self._push_fn = None

    # ── 依赖注入 ──

    def bind_dispatch(self, dispatch_fn):
        """绑定下发函数（注入 dispatch_service.dispatch）"""
        self._dispatch_fn = dispatch_fn

    def bind_push(self, push_fn):
        """绑定推送函数（注入 push_service.push_status）"""
        self._push_fn = push_fn

    # ── 生命周期 ──

    async def start(self):
        """启动后台任务，并从数据库恢复注册表"""
        if self._running:
            return
        self._running = True

        # 从数据库恢复注册信息
        await self._restore_registry()

        self._worker_task = asyncio.create_task(self._queue_worker())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        logger.info("任务调度器已启动（队列 worker + 心跳监控 + 主动轮询）")

    async def stop(self):
        """停止后台任务"""
        self._running = False
        for task in [self._worker_task, self._heartbeat_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("任务调度器已停止")

    async def _restore_registry(self):
        """从数据库恢复所有在线注册信息到内存缓存"""
        from cloud.db.engine import async_session_factory
        from cloud.db.crud import launcher_get_all

        try:
            async with async_session_factory() as db:
                launchers = await launcher_get_all(db)
                for l in launchers:
                    self._local_registry[l.user_id] = LocalRegistration(
                        user_id=l.user_id,
                        host=l.host,
                        port=l.port,
                        version=l.version,
                        status=l.status,
                        registered_at=l.registered_at,
                        last_heartbeat=l.last_heartbeat,
                    )
            logger.info(f"已从数据库恢复 {len(self._local_registry)} 个注册")
        except Exception:
            logger.warning("数据库恢复注册表失败，从空注册表启动", exc_info=True)

    # ── 公共 API ──

    async def enqueue(self, task: WorkflowTask) -> int:
        """
        将任务加入优先级队列。

        Args:
            task: 工作流任务

        Returns:
            int: 当前队列位置（0 = 即将执行）
        """
        task.status = TaskStatus.QUEUED
        entry = (task.priority.value, time.monotonic(), task)
        await self._queue.put(entry)
        position = self._queue.qsize()
        logger.info(f"任务已入队: {task.task_id} (priority={task.priority.name}, position={position})")
        return position

    def get_queue_size(self) -> int:
        """获取当前队列大小"""
        return self._queue.qsize()

    # ── 本地引擎注册 ──

    async def register_local(self, user_id: str, host: str, port: int, version: str = "1.0.0"):
        """注册本地引擎（内存 + 数据库）"""
        from cloud.db.engine import async_session_factory
        from cloud.db.crud import launcher_upsert

        # 内存缓存
        reg = LocalRegistration(
            user_id=user_id,
            host=host,
            port=port,
            version=version,
            status="online",
        )
        self._local_registry[user_id] = reg

        # 持久化
        try:
            async with async_session_factory() as db:
                await launcher_upsert(db, user_id, host, port, version)
        except Exception:
            logger.exception("数据库持久化注册失败")

        logger.info(f"本地引擎已注册: {user_id} → {host}:{port} (v{version})")

    async def unregister_local(self, user_id: str):
        """注销本地引擎（内存 + 数据库）"""
        from cloud.db.engine import async_session_factory
        from cloud.db.crud import launcher_delete

        self._local_registry.pop(user_id, None)

        try:
            async with async_session_factory() as db:
                await launcher_delete(db, user_id)
        except Exception:
            logger.exception("数据库删除注册失败")

        logger.info(f"本地引擎已注销: {user_id}")

    async def heartbeat(self, user_id: str, host: str, port: int, version: str = "1.0.0",
                        active_tasks: int = 0, gpu_available: bool = True) -> bool:
        """
        处理本地引擎心跳。

        Args:
            user_id: 用户 ID
            host: 本地服务 IP
            port: 本地服务端口
            version: 引擎版本
            active_tasks: 当前活跃任务数
            gpu_available: GPU 是否可用

        Returns:
            bool: 是否为新注册（首次心跳）
        """
        is_new = user_id not in self._local_registry

        if is_new:
            await self.register_local(user_id, host, port, version)
        else:
            # 更新内存缓存
            reg = self._local_registry[user_id]
            reg.last_heartbeat = datetime.now(timezone.utc)
            reg.host = host
            reg.port = port
            reg.version = version
            reg.status = "online"

            # 持久化心跳
            from cloud.db.engine import async_session_factory
            from cloud.db.crud import launcher_update_heartbeat
            try:
                async with async_session_factory() as db:
                    await launcher_update_heartbeat(db, user_id, host, port, version)
            except Exception:
                logger.exception("数据库更新心跳失败")

        logger.debug(f"心跳: {user_id} (tasks={active_tasks}, gpu={gpu_available})")
        return is_new

    def get_local_url(self, user_id: str) -> Optional[str]:
        """获取本地引擎 URL"""
        reg = self._local_registry.get(user_id)
        if reg and reg.status == "online":
            return f"http://{reg.host}:{reg.port}"
        return None

    def get_registration(self, user_id: str) -> Optional[LocalRegistration]:
        """获取本地引擎注册信息"""
        return self._local_registry.get(user_id)

    def get_all_registrations(self) -> Dict[str, LocalRegistration]:
        """获取所有注册信息"""
        return dict(self._local_registry)

    def is_local_online(self, user_id: str) -> bool:
        """检查本地引擎是否在线"""
        reg = self._local_registry.get(user_id)
        return reg is not None and reg.status == "online"

    # ── 后台任务 ──

    async def _queue_worker(self):
        """队列消费循环：按优先级顺序执行任务"""
        logger.info("队列 worker 已启动")
        while self._running:
            try:
                # 阻塞等待任务（1s 超时以响应停止信号）
                try:
                    priority, ts, task = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # 执行任务
                await self._execute_task(task)
                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("队列 worker 异常")

        logger.info("队列 worker 已停止")

    async def _execute_task(self, task: WorkflowTask):
        """
        执行单个任务（含自动重试）。

        流程：
        1. 意图理解 → 生成工作流 JSON
        2. HTTP POST 下发到本地引擎
        3. 失败时指数退避重试（最多 3 次）
        """
        for attempt in range(task.max_retries + 1):
            try:
                if attempt > 0:
                    task.status = TaskStatus.RETRYING
                    task.retry_count = attempt
                    await self._push_status(task, f"重试中 (第 {attempt}/{task.max_retries} 次)")
                    backoff = RETRY_BACKOFF_BASE ** (attempt - 1)
                    logger.info(f"任务重试: {task.task_id} attempt={attempt}, backoff={backoff}s")
                    await asyncio.sleep(backoff)

                # 调用下发服务（同步调用，在线程池中执行）
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    self._dispatch_sync,
                    task,
                )

                # 下发成功
                await self._push_status(task, "已下发到本地引擎")
                logger.info(f"任务下发成功: {task.task_id}")
                return

            except Exception as e:
                logger.warning(f"任务下发失败: {task.task_id} attempt={attempt}: {e}")

                if attempt >= task.max_retries:
                    # 所有重试耗尽
                    task.status = TaskStatus.FAILED
                    task.error = f"下发失败（已重试 {task.max_retries} 次）: {str(e)}"
                    task.completed_at = datetime.now(timezone.utc)
                    await self._push_status(task, f"任务失败: {task.error}")
                    logger.error(f"任务彻底失败: {task.task_id}")
                # 否则继续重试循环

    def _dispatch_sync(self, task: WorkflowTask):
        """
        同步下发逻辑（在线程池中执行，避免阻塞事件循环）。

        调用现有的 dispatch_service 执行意图理解 + HTTP 下发。
        """
        from cloud.services.dispatch import dispatch_service

        # 解析本地 URL
        local_url = task.local_url
        if not local_url:
            local_url = self.get_local_url(task.user_id)
            if not local_url:
                raise RuntimeError(f"用户 {task.user_id} 的本地引擎未注册或已离线")

        task.local_url = local_url

        # 意图理解
        from cloud.intent.engine import engine
        workflow = engine.process(
            user_input=task.user_input,
            assets=task.assets,
            project_id=task.project_id,
        )
        task.workflow = workflow

        # 下发到本地
        import requests
        url = f"{local_url.rstrip('/')}/api/v1/local/execute"
        payload = {"task_id": task.task_id, "workflow": workflow}

        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()

        task.status = TaskStatus.DISPATCHED
        task.dispatched_at = datetime.now(timezone.utc)

    async def _push_status(self, task: WorkflowTask, message: str):
        """通过 PushService 推送任务状态变更"""
        if self._push_fn is None:
            return
        try:
            await self._push_fn(task.user_id, {
                "task_id": task.task_id,
                "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
                "progress": task.progress,
                "retry_count": task.retry_count,
                "error": task.error,
                "message": message,
            })
        except Exception:
            logger.exception("推送状态失败")

    async def _heartbeat_monitor(self):
        """
        心跳监控循环 + 主动轮询。

        每 HEARTBEAT_INTERVAL 秒：
        1. 检查所有注册的心跳超时
        2. 对超时的启动器，主动 HTTP GET 探活
        3. 确认离线后标记为 timeout，推送通知
        """
        logger.info(
            f"心跳监控已启动 "
            f"(interval={HEARTBEAT_INTERVAL}s, timeout={HEARTBEAT_TIMEOUT}s, "
            f"active_poll_timeout={ACTIVE_POLL_TIMEOUT}s)"
        )
        while self._running:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await self._check_and_poll()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("心跳监控异常")

        logger.info("心跳监控已停止")

    async def _check_and_poll(self):
        """
        检查心跳超时 + 主动轮询探活。

        流程：
        1. 找出所有心跳超时的启动器
        2. 对每个超时启动器，主动 HTTP GET /health
        3. 如果响应正常 → 恢复为 online（可能是网络抖动）
        4. 如果无响应 → 标记为 timeout，推送离线通知
        """
        now = datetime.now(timezone.utc)
        timeout_users = []

        # ── 第一步：找出心跳超时的启动器 ──
        for user_id, reg in list(self._local_registry.items()):
            elapsed = (now - reg.last_heartbeat).total_seconds()
            if elapsed > HEARTBEAT_TIMEOUT and reg.status == "online":
                timeout_users.append((user_id, reg, elapsed))

        if not timeout_users:
            return

        # ── 第二步：主动 HTTP 轮询探活 ──
        async with httpx.AsyncClient(timeout=ACTIVE_POLL_TIMEOUT) as client:
            for user_id, reg, elapsed in timeout_users:
                health_url = f"http://{reg.host}:{reg.port}/health"
                is_alive = await self._active_poll(client, health_url)

                if is_alive:
                    # 启动器还活着，只是心跳延迟，恢复在线状态
                    reg.last_heartbeat = now
                    reg.status = "online"
                    logger.info(
                        f"主动探活成功: {user_id} @ {health_url} "
                        f"(心跳延迟 {elapsed:.0f}s，已恢复在线)"
                    )
                else:
                    # 确认离线
                    reg.status = "timeout"
                    logger.warning(
                        f"本地引擎已离线: {user_id} @ {health_url} "
                        f"(最后心跳 {elapsed:.0f}s 前，主动探活失败)"
                    )

                    # 持久化离线状态
                    from cloud.db.engine import async_session_factory
                    from cloud.db.crud import launcher_set_status
                    try:
                        async with async_session_factory() as db:
                            await launcher_set_status(db, user_id, "timeout")
                    except Exception:
                        logger.exception("数据库更新离线状态失败")

                    # 异步推送离线通知
                    if self._push_fn is not None:
                        asyncio.ensure_future(
                            self._push_fn(user_id, {
                                "type": "local_status",
                                "status": "offline",
                                "user_id": user_id,
                                "message": (
                                    f"本地引擎已离线（{elapsed:.0f}s 未心跳，"
                                    f"主动探活 {health_url} 失败）"
                                ),
                            })
                        )

    async def _active_poll(self, client: httpx.AsyncClient, health_url: str) -> bool:
        """
        主动 HTTP GET 探活。

        Args:
            client: httpx 异步客户端
            health_url: 启动器健康检查端点

        Returns:
            bool: True = 启动器存活，False = 确认离线
        """
        try:
            response = await client.get(health_url)
            return response.status_code == 200
        except Exception:
            return False


# ── 全局单例 ──
task_scheduler = TaskScheduler()