"""
Memento-X 工作流管道

封装从云端意图理解到本地工具执行的完整链路。
"""
import json
import logging
import httpx
from typing import Optional
from local.scheduler.executor import WorkflowExecutor

logger = logging.getLogger(__name__)

CLOUD_API_URL = "http://localhost:8000/api/v1"


class Pipeline:
    """Memento-X 处理管道"""

    def __init__(self, api_base: str = CLOUD_API_URL, token: str = ""):
        self.api_base = api_base
        self.token = token
        self.executor = WorkflowExecutor()

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def process(self, user_input: str, context: Optional[dict] = None) -> dict:
        """
        完整处理流程：用户输入 → 云端意图理解 → 本地执行

        Args:
            user_input: 用户自然语言输入
            context: 可选的上下文

        Returns:
            dict: {"success": bool, "results": {...}, "errors": {...}}
        """
        # 1. 发送意图理解请求到云端
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.api_base}/intent/understand",
                json={"input": user_input, "context": context},
                headers=self._headers,
            )

            if response.status_code != 200:
                return {"success": False, "error": f"云端请求失败: {response.status_code}"}

            intent = response.json()

        if not intent.get("success"):
            return {
                "success": False,
                "error": intent.get("error", "意图理解失败"),
            }

        workflow = intent.get("workflow", {})
        understood = intent.get("understood", "")

        logger.info(f"AI 理解: {understood}")
        logger.debug(f"工作流: {json.dumps(workflow, ensure_ascii=False, indent=2)}")

        # 2. 本地执行工作流
        result = self.executor.execute(workflow)

        # 3. 回传状态到云端
        await self._report_status(result, workflow.get("workflow_id", ""))

        return result

    async def _report_status(self, result: dict, workflow_id: str):
        """回传执行状态到云端"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{self.api_base}/status/report",
                    json={
                        "task_id": workflow_id,
                        "status": result.get("status", "failed"),
                        "progress": 1.0 if result.get("status") == "success" else result.get("progress", 0),
                        "error": result.get("errors", {}).get("_workflow", ""),
                    },
                    headers=self._headers,
                )
        except Exception as e:
            logger.warning(f"状态回传失败: {e}")


# 全局管道
pipeline = Pipeline()