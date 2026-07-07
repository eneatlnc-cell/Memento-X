"""
Memento-X 统一调度器

接收云端 JSON 工作流，解析并顺序/并行执行工具调用。
"""
import json
import time
import asyncio
from typing import List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from local.tools import birefnet, sam2, comfyui, ffmpeg, davinci, hyperframes


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """单个步骤的执行结果"""
    index: int
    action: str
    status: StepStatus = StepStatus.PENDING
    output_path: str = ""
    error: str = ""
    duration_ms: int = 0


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    success: bool = False
    steps: List[StepResult] = field(default_factory=list)
    final_output: str = ""
    total_duration_ms: int = 0
    error: str = ""


# 工具调度表
TOOL_EXECUTORS = {
    "matting": birefnet,
    "tracking": sam2,
    "replace": comfyui,
    "effect": comfyui,
    "composite": ffmpeg,
    "color_grade": davinci,
    "subtitle": hyperframes,
    "crop": ffmpeg,
    "stabilize": ffmpeg,
    "denoise": ffmpeg,
}


class Scheduler:
    """统一调度器 — 解析 JSON 工作流并执行"""

    def __init__(self, workspace: str = "~/.memento/workspace"):
        self.workspace = workspace
        self._on_step_update: Optional[Callable] = None

    def on_step_update(self, callback: Callable):
        """注册步骤状态更新回调（用于 UI 进度显示）"""
        self._on_step_update = callback

    async def execute(self, workflow_json: str | dict) -> WorkflowResult:
        """
        执行工作流。

        Args:
            workflow_json: 云端下发的 JSON 工作流（字符串或字典）

        Returns:
            WorkflowResult: 执行结果
        """
        if isinstance(workflow_json, str):
            workflow = json.loads(workflow_json)
        else:
            workflow = workflow_json

        steps = workflow.get("steps", [])
        if not steps:
            return WorkflowResult(success=False, error="工作流为空")

        result = WorkflowResult(success=True)
        start_time = time.time()

        # 顺序执行步骤（部分步骤可并行，后续优化）
        for i, step in enumerate(steps):
            action = step.get("action", "")
            params = step.get("params", {})

            step_result = StepResult(index=i, action=action)
            result.steps.append(step_result)

            executor = TOOL_EXECUTORS.get(action)
            if not executor:
                step_result.status = StepStatus.SKIPPED
                step_result.error = f"未知工具: {action}"
                self._notify(step_result)
                continue

            step_result.status = StepStatus.RUNNING
            self._notify(step_result)

            try:
                t0 = time.time()
                output = await executor.execute(
                    action=action,
                    params=params,
                    workspace=self.workspace,
                    previous_output=result.steps[i - 1].output_path if i > 0 else None,
                )
                step_result.status = StepStatus.COMPLETED
                step_result.output_path = output or ""
                step_result.duration_ms = int((time.time() - t0) * 1000)
            except Exception as e:
                step_result.status = StepStatus.FAILED
                step_result.error = str(e)
                result.success = False
                self._notify(step_result)
                break

            self._notify(step_result)

        result.total_duration_ms = int((time.time() - start_time) * 1000)
        result.final_output = result.steps[-1].output_path if result.steps else ""

        return result

    def _notify(self, step: StepResult):
        if self._on_step_update:
            self._on_step_update(step)


# 全局调度器
scheduler = Scheduler()