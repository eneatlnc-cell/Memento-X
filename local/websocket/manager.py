"""
Memento-X WebSocket 连接管理器

管理 WebSocket 连接，支持：
- 按 task_id 推送状态
- 广播全局消息
- 连接心跳检测
"""
import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    WebSocket 连接管理器。

    使用方式：
        ws_manager = WebSocketManager()

        # 在 WebSocket 路由中
        await ws_manager.connect(websocket, task_id)

        # 在调度器回调中
        ws_manager.push_status(task_id, {"status": "running"})
    """

    def __init__(self):
        # task_id → 该任务订阅的 WebSocket 连接集合
        self._task_connections: Dict[str, Set[WebSocket]] = {}
        # 全局连接（未指定 task_id 的）
        self._global_connections: Set[WebSocket] = set()
        # 连接心跳记录
        self._heartbeats: Dict[WebSocket, float] = {}

    async def connect(self, websocket: WebSocket, task_id: Optional[str] = None):
        """
        接受 WebSocket 连接。

        Args:
            websocket: WebSocket 连接
            task_id: 订阅的任务 ID（可选，不指定则接收全局广播）
        """
        await websocket.accept()
        self._heartbeats[websocket] = time.time()

        if task_id:
            if task_id not in self._task_connections:
                self._task_connections[task_id] = set()
            self._task_connections[task_id].add(websocket)
            logger.debug(f"WebSocket 已连接: task={task_id}")
        else:
            self._global_connections.add(websocket)
            logger.debug("WebSocket 已连接: global")

        # 发送确认消息
        await websocket.send_json({
            "type": "connected",
            "task_id": task_id,
            "message": "WebSocket 连接已建立",
        })

    def disconnect(self, websocket: WebSocket):
        """
        断开 WebSocket 连接。

        Args:
            websocket: WebSocket 连接
        """
        # 从任务连接中移除
        for task_id, connections in list(self._task_connections.items()):
            if websocket in connections:
                connections.discard(websocket)
                if not connections:
                    del self._task_connections[task_id]
                logger.debug(f"WebSocket 已断开: task={task_id}")

        # 从全局连接中移除
        self._global_connections.discard(websocket)

        # 清理心跳
        self._heartbeats.pop(websocket, None)

    async def push_status(self, task_id: str, data: dict):
        """
        推送任务状态到所有订阅该任务的 WebSocket 连接。

        Args:
            task_id: 任务 ID
            data: 状态数据
        """
        message = {
            "type": "status_update",
            "task_id": task_id,
            "timestamp": time.time(),
            "data": data,
        }

        # 推送到任务订阅者
        connections = self._task_connections.get(task_id, set())
        dead = set()

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)

        # 清理死连接
        for ws in dead:
            self.disconnect(ws)

        # 推送到全局订阅者
        dead = set()
        for ws in self._global_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)

        for ws in dead:
            self.disconnect(ws)

    async def broadcast(self, data: dict):
        """
        广播消息到所有连接。

        Args:
            data: 消息数据
        """
        message = {
            "type": "broadcast",
            "timestamp": time.time(),
            "data": data,
        }

        all_connections = set(self._global_connections)
        for connections in self._task_connections.values():
            all_connections.update(connections)

        dead = set()
        for ws in all_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)

        for ws in dead:
            self.disconnect(ws)

    async def handle_heartbeat(self, websocket: WebSocket):
        """处理心跳"""
        self._heartbeats[websocket] = time.time()

    def get_active_connections_count(self) -> int:
        """获取活跃连接数"""
        count = len(self._global_connections)
        for connections in self._task_connections.values():
            count += len(connections)
        return count

    def get_task_subscribers_count(self, task_id: str) -> int:
        """获取订阅某任务的连接数"""
        return len(self._task_connections.get(task_id, set()))


# ── 全局单例 ──
ws_manager = WebSocketManager()