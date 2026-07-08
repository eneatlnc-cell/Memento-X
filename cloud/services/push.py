"""
Memento-X 云端状态推送服务

管理云端 → 客户端的实时状态推送（WebSocket / SSE）。

支持：
- 任务状态实时推送
- 进度更新
- 错误通知
"""
import asyncio
import json
import logging
import time
from typing import Dict, Set, Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class PushService:
    """
    状态推送服务。

    管理云端 WebSocket 连接，向客户端（Memento-X UI / Memento-App）推送实时状态。

    使用方式：
        push_service = PushService()

        # WebSocket 路由中
        await push_service.connect(websocket, user_id)

        # 下发服务中
        push_service.push_status(user_id, {"task_id": "xxx", "status": "running"})
    """

    def __init__(self):
        # user_id → WebSocket 连接集合
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._heartbeats: Dict[WebSocket, float] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """
        接受客户端 WebSocket 连接。

        Args:
            websocket: WebSocket 连接
            user_id: 用户 ID
        """
        await websocket.accept()

        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)
        self._heartbeats[websocket] = time.time()

        logger.info(f"客户端已连接: user={user_id}")

        await websocket.send_json({
            "type": "connected",
            "user_id": user_id,
            "message": "已连接到 Memento-X Cloud",
        })

    def disconnect(self, websocket: WebSocket, user_id: Optional[str] = None):
        """
        断开连接。

        Args:
            websocket: WebSocket 连接
            user_id: 用户 ID（可选，用于加速查找）
        """
        if user_id and user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
        else:
            for uid, connections in list(self._connections.items()):
                if websocket in connections:
                    connections.discard(websocket)
                    if not connections:
                        del self._connections[uid]
                    break

        self._heartbeats.pop(websocket, None)

    async def push_status(self, user_id: str, data: dict):
        """
        推送状态到指定用户的所有连接。

        Args:
            user_id: 用户 ID
            data: 状态数据
        """
        message = {
            "type": "task_update",
            "timestamp": time.time(),
            "data": data,
        }

        connections = self._connections.get(user_id, set())
        dead = set()

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)

        for ws in dead:
            self.disconnect(ws, user_id)

    async def push_error(self, user_id: str, error: str, task_id: Optional[str] = None):
        """
        推送错误通知。

        Args:
            user_id: 用户 ID
            error: 错误信息
            task_id: 任务 ID
        """
        await self.push_status(user_id, {
            "type": "error",
            "task_id": task_id,
            "error": error,
        })

    async def broadcast(self, data: dict):
        """广播消息到所有连接"""
        message = {
            "type": "broadcast",
            "timestamp": time.time(),
            "data": data,
        }

        dead = set()
        for user_id, connections in self._connections.items():
            for ws in connections:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.add((ws, user_id))

        for ws, uid in dead:
            self.disconnect(ws, uid)

    def get_connection_count(self) -> int:
        """获取总连接数"""
        return sum(len(conns) for conns in self._connections.values())

    def get_user_connection_count(self, user_id: str) -> int:
        """获取某用户的连接数"""
        return len(self._connections.get(user_id, set()))


# ── 全局单例 ──
push_service = PushService()