"""
Memento-X 本地 API 服务

FastAPI 服务，作为云端下发工作流的接收端。

启动方式：
    python -m local.api.server
    uvicorn local.api.server:app --host 0.0.0.0 --port 8000

功能：
1. 接收工作流 JSON
2. 调用调度器执行
3. 返回执行结果
4. WebSocket 实时状态推送
5. 向云端注册本地服务地址
"""
import logging
import os
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from local.api.routes import router, set_executor
from local.scheduler import WorkflowExecutor
from local.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

# ── 配置默认值 ──
DEFAULT_PORT = int(os.getenv("LOCAL_API_PORT", "8000"))
DEFAULT_HOST = os.getenv("LOCAL_API_HOST", "0.0.0.0")
DEFAULT_TOOLS_DIR = os.getenv("TOOLS_DIR", "local/tools/")
DEFAULT_ASSETS_DIR = os.getenv("ASSETS_DIR", os.path.expanduser("~/.memento/assets"))
DEFAULT_WORKSPACE = os.getenv("WORKSPACE_DIR", os.path.expanduser("~/.memento/workspace"))
CLOUD_REGISTRY_URL = os.getenv("CLOUD_REGISTRY_URL", "")  # 云端注册地址


class LocalAPIServer:
    """
    本地 API 服务器。

    使用方式：
        server = LocalAPIServer(port=8000, tools_dir="local/tools/")
        server.start()
    """

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        host: str = DEFAULT_HOST,
        tools_dir: str = DEFAULT_TOOLS_DIR,
        assets_dir: Optional[str] = DEFAULT_ASSETS_DIR,
        workspace: str = DEFAULT_WORKSPACE,
        cloud_registry_url: Optional[str] = CLOUD_REGISTRY_URL,
    ):
        self.port = port
        self.host = host
        self.tools_dir = tools_dir
        self.assets_dir = assets_dir
        self.workspace = workspace
        self.cloud_registry_url = cloud_registry_url

        # 创建调度器
        self.executor = WorkflowExecutor(
            tools_dir=tools_dir,
            assets_dir=assets_dir,
            workspace=workspace,
        )
        set_executor(self.executor)

        # 创建 FastAPI 应用
        self.app = self._create_app()

        logger.info(
            f"LocalAPIServer 初始化完成: "
            f"host={host}, port={port}, "
            f"tools={self.executor.registry.count()}, "
            f"assets={'enabled' if assets_dir else 'disabled'}"
        )

    def _create_app(self) -> FastAPI:
        """创建 FastAPI 应用"""
        app = FastAPI(
            title="Memento-X Local API",
            description="本地调度器 API — 接收云端工作流 JSON 并执行",
            version="0.1.0",
        )

        # CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 注册路由
        app.include_router(router, prefix="/api/v1/local", tags=["local"])

        # ── WebSocket 端点 ──

        @app.websocket("/ws/{task_id}")
        async def websocket_task(websocket: WebSocket, task_id: str):
            """订阅特定任务的实时状态"""
            await ws_manager.connect(websocket, task_id)
            try:
                while True:
                    # 保持连接，接收心跳
                    data = await websocket.receive_text()
                    if data == "ping":
                        await ws_manager.handle_heartbeat(websocket)
                        await websocket.send_text("pong")
            except WebSocketDisconnect:
                ws_manager.disconnect(websocket)
            except Exception:
                ws_manager.disconnect(websocket)

        @app.websocket("/ws")
        async def websocket_global(websocket: WebSocket):
            """全局状态推送（所有任务）"""
            await ws_manager.connect(websocket)
            try:
                while True:
                    data = await websocket.receive_text()
                    if data == "ping":
                        await ws_manager.handle_heartbeat(websocket)
                        await websocket.send_text("pong")
            except WebSocketDisconnect:
                ws_manager.disconnect(websocket)
            except Exception:
                ws_manager.disconnect(websocket)

        @app.get("/health")
        async def health():
            """健康检查"""
            return {
                "status": "ok",
                "service": "Memento-X Local API",
                "version": "0.1.0",
                "tools": self.executor.registry.count(),
                "ws_connections": ws_manager.get_active_connections_count(),
            }

        return app

    def start(self, blocking: bool = True):
        """
        启动服务。

        Args:
            blocking: True 阻塞运行，False 后台线程运行
        """
        logger.info(f"启动本地 API 服务: http://{self.host}:{self.port}")

        if self.cloud_registry_url:
            self._register_with_cloud()

        if blocking:
            uvicorn.run(self.app, host=self.host, port=self.port, log_level="info")
        else:
            thread = threading.Thread(
                target=uvicorn.run,
                args=(self.app,),
                kwargs={"host": self.host, "port": self.port, "log_level": "info"},
                daemon=True,
            )
            thread.start()
            logger.info("本地 API 服务已在后台启动")

    def stop(self):
        """停止服务"""
        if self.cloud_registry_url:
            self._unregister_from_cloud()
        logger.info("本地 API 服务已停止")

    def _register_with_cloud(self):
        """向云端注册本地服务地址"""
        if not self.cloud_registry_url:
            return
        try:
            import requests
            requests.post(
                f"{self.cloud_registry_url}/api/v1/local/register",
                json={"host": self.host, "port": self.port},
                timeout=5,
            )
            logger.info(f"已向云端注册: {self.cloud_registry_url}")
        except Exception as e:
            logger.warning(f"云端注册失败: {e}")

    def _unregister_from_cloud(self):
        """从云端注销"""
        if not self.cloud_registry_url:
            return
        try:
            import requests
            requests.post(
                f"{self.cloud_registry_url}/api/v1/local/unregister",
                json={"host": self.host, "port": self.port},
                timeout=5,
            )
            logger.info("已从云端注销")
        except Exception:
            pass


# ── 模块级 FastAPI 应用（供 uvicorn 直接使用） ──

def create_app() -> FastAPI:
    """创建 FastAPI 应用（工厂函数）"""
    server = LocalAPIServer()
    return server.app


# 默认应用实例
app = create_app()

# ── 入口 ──

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    server = LocalAPIServer()
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()