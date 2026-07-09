"""
Memento-X 云端 WebSocket 推送服务

提供实时的任务状态推送和连接管理。

功能：
- WebSocket 连接管理（按 user_id 分组）
- 任务状态变更推送
- 本地引擎状态推送
- 服务端主动心跳（ping/pong 保活）
- 僵尸连接清理（60s 无响应断开）
"""
import asyncio
import json
import logging
import time
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# 心跳配置
PING_INTERVAL = 30     # 服务端发送 ping 的间隔（秒）
PONG_TIMEOUT = 10      # 等待 pong 的超时（秒）
CONNECTION_TTL = 90    # 连接最大空闲时间（秒），超时强制断开


class PushService:
    """
    WebSocket 推送服务。

    使用方式：
        push_service = PushService()

        # 在 WebSocket 路由中：
        await push_service.connect(websocket, user_id)
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await push_service.handle_ping(websocket, user_id)
        finally:
            push_service.disconnect(websocket, user_id)

        # 在其他服务中推送：
        await push_service.push_status(user_id, {"task_id": "...", "status": "running"})
    """

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}  # user_id → WebSocket 集合
        self._last_active: Dict[WebSocket, float] = {}      # WebSocket → 最后活跃时间戳
        self._cleanup_task: Optional[asyncio.Task] = None

    # ── 生命周期 ──

    async def start(self):
        """启动后台清理任务"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("PushService 已启动（连接清理循环）")

    async def stop(self):
        """停止后台清理任务"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        # 断开所有连接
        for user_id, sockets in list(self._connections.items()):
            for ws in list(sockets):
                await self._disconnect(ws, user_id)
        logger.info("PushService 已停止")

    # ── 连接管理 ──

    async def connect(self, websocket: WebSocket, user_id: str):
        """
        接受 WebSocket 连接。

        Args:
            websocket: WebSocket 连接
            user_id: 用户 ID
        """
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)
        self._last_active[websocket] = time.time()
        logger.info(f"WebSocket 已连接: user={user_id} (total={self.get_connection_count()})")

    def disconnect(self, websocket: WebSocket, user_id: Optional[str] = None):
        """
        断开 WebSocket 连接（同步清理，不等待）。

        Args:
            websocket: WebSocket 连接
            user_id: 用户 ID（可选，如未提供则遍历查找）
        """
        asyncio.ensure_future(self._disconnect(websocket, user_id))

    async def _disconnect(self, websocket: WebSocket, user_id: Optional[str] = None):
        """异步断开连接并清理"""
        self._last_active.pop(websocket, None)

        if user_id:
            sockets = self._connections.get(user_id, set())
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(user_id, None)
        else:
            for uid, sockets in list(self._connections.items()):
                if websocket in sockets:
                    sockets.discard(websocket)
                    if not sockets:
                        self._connections.pop(uid, None)
                    break

        try:
            await websocket.close()
        except Exception:
            pass

        logger.debug(f"WebSocket 已断开: user={user_id} (total={self.get_connection_count()})")

    # ── 推送 ──

    async def push_status(self, user_id: str, data: dict):
        """
        推送任务状态到指定用户的所有 WebSocket 连接。

        Args:
            user_id: 用户 ID
            data: 推送数据
        """
        sockets = self._connections.get(user_id, set())
        if not sockets:
            return

        message = json.dumps(data, ensure_ascii=False)
        dead = set()

        for ws in sockets:
            try:
                await ws.send_text(message)
                self._last_active[ws] = time.time()
            except Exception:
                dead.add(ws)

        # 清理死连接
        for ws in dead:
            await self._disconnect(ws, user_id)

    async def push_error(self, user_id: str, error: str, task_id: Optional[str] = None):
        """
        推送错误到指定用户。

        Args:
            user_id: 用户 ID
            error: 错误消息
            task_id: 关联的任务 ID（可选）
        """
        await self.push_status(user_id, {
            "type": "error",
            "task_id": task_id,
            "error": error,
        })

    async def broadcast(self, data: dict):
        """广播消息到所有连接"""
        message = json.dumps(data, ensure_ascii=False)
        dead = []

        for user_id, sockets in list(self._connections.items()):
            for ws in sockets:
                try:
                    await ws.send_text(message)
                    self._last_active[ws] = time.time()
                except Exception:
                    dead.append((ws, user_id))

        for ws, uid in dead:
            await self._disconnect(ws, uid)

    async def push_local_status(self, user_id: str, status: str, message: str = ""):
        """
        推送本地引擎状态变更。

        Args:
            user_id: 用户 ID
            status: 状态 ("online" | "offline" | "timeout")
            message: 状态描述
        """
        await self.push_status(user_id, {
            "type": "local_status",
            "status": status,
            "message": message,
        })

    # ── 心跳处理 ──

    async def handle_ping(self, websocket: WebSocket, user_id: str):
        """处理客户端 ping → 回复 pong"""
        try:
            await websocket.send_text("pong")
            self._last_active[websocket] = time.time()
        except Exception:
            await self._disconnect(websocket, user_id)

    async def _send_ping(self, websocket: WebSocket, user_id: str) -> bool:
        """发送服务端 ping，返回是否成功"""
        try:
            await websocket.send_text("ping")
            self._last_active[websocket] = time.time()
            return True
        except Exception:
            await self._disconnect(websocket, user_id)
            return False

    # ── 后台任务 ──

    async def _cleanup_loop(self):
        """
        连接清理循环。

        每 PING_INTERVAL 秒：
        1. 向所有连接发送 ping
        2. 超过 CONNECTION_TTL 秒无活动的连接强制断开
        """
        logger.info(f"连接清理循环已启动 (interval={PING_INTERVAL}s, ttl={CONNECTION_TTL}s)")
        while True:
            try:
                await asyncio.sleep(PING_INTERVAL)

                now = time.time()
                dead = []

                for user_id, sockets in list(self._connections.items()):
                    for ws in sockets:
                        last = self._last_active.get(ws, 0)
                        if now - last > CONNECTION_TTL:
                            # 超时强制断开
                            dead.append((ws, user_id))
                            logger.info(f"连接超时断开: user={user_id} (idle={now - last:.0f}s)")
                        else:
                            # 发送 ping 保活
                            await self._send_ping(ws, user_id)

                for ws, uid in dead:
                    await self._disconnect(ws, uid)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("连接清理循环异常")

        logger.info("连接清理循环已停止")

    # ── 查询 ──

    def get_connection_count(self) -> int:
        """获取总连接数"""
        return sum(len(s) for s in self._connections.values())

    def get_user_connection_count(self, user_id: str) -> int:
        """获取指定用户的连接数"""
        return len(self._connections.get(user_id, set()))


# ── 全局单例 ──
push_service = PushService()