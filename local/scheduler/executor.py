"""
Memento-X 统一调度器

接收云端 JSON 工作流，解析并顺序/并行执行工具调用。

素材库集成：
- 调度器维护本地素材路径映射表（asset_id → 本地文件路径）
- 执行 replace 步骤时，检查 asset_id 并解析为本地路径
- 如果 requires_download=true，返回友好提示给用户
"""
import json
import time
import asyncio
import os
from typing import List, Optional, Callable, Dict
from dataclasses import dataclass, field
from enum import Enum

from local.tools import birefnet, sam2, comfyui, ffmpeg, davinci, hyperframes


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_ASSET = "needs_asset"  # 需要用户上传素材


@dataclass
class StepResult:
    """单个步骤的执行结果"""
    index: int
    action: str
    status: StepStatus = StepStatus.PENDING
    output_path: str = ""
    error: str = ""
    duration_ms: int = 0
    missing_assets: List[str] = field(default_factory=list)  # 缺失的素材名称列表


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    success: bool = False
    steps: List[StepResult] = field(default_factory=list)
    final_output: str = ""
    total_duration_ms: int = 0
    error: str = ""
    missing_assets: List[str] = field(default_factory=list)  # 全局缺失素材汇总


# 工具调度表
TOOL_EXECUTORS = {
    "matting": birefnet,
    "track": sam2,
    "replace": comfyui,
    "effect": comfyui,
    "composite": ffmpeg,
    "color": ffmpeg,
    "color_grade": davinci,
    "subtitle": hyperframes,
    "crop": ffmpeg,
    "stabilize": ffmpeg,
    "denoise": ffmpeg,
    "export": ffmpeg,
    "render": ffmpeg,
}


class Scheduler:
    """统一调度器 — 解析 JSON 工作流并执行"""

    def __init__(self, workspace: str = "~/.memento/workspace"):
        self.workspace = os.path.expanduser(workspace)
        self._on_step_update: Optional[Callable] = None
        self._asset_map: Dict[str, str] = {}  # asset_id → 本地路径

    def set_assets(self, assets: list):
        """
        设置素材库映射表。

        Args:
            assets: 素材列表 [{"id": "asset_001", "path": "/assets/ironman.png"}, ...]
        """
        self._asset_map = {a["id"]: a["path"] for a in assets if a.get("id") and a.get("path")}

    def _resolve_asset_path(self, asset_id: Optional[str]) -> Optional[str]:
        """
        根据 asset_id 解析本地素材路径。

        Args:
            asset_id: 素材 ID，null 表示无引用

        Returns:
            本地文件路径，或 None（asset_id 为 null 或未找到）
        """
        if not asset_id:
            return None
        return self._asset_map.get(asset_id)

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

        for i, step in enumerate(steps):
            action = step.get("action", "")
            params = dict(step.get("params", {}))  # 复制，避免修改原始数据

            step_result = StepResult(index=i, action=action)
            result.steps.append(step_result)

            # ── 素材预处理：解析 asset_id ──
            if action == "replace":
                asset_id = params.get("asset_id")
                requires_download = params.get("requires_download", False)
                missing = params.get("missing_asset", "")

                if asset_id:
                    # 有 asset_id，解析为本地路径
                    local_path = self._resolve_asset_path(asset_id)
                    if local_path:
                        params["reference_image"] = local_path
                    else:
                        # asset_id 存在但本地路径未找到
                        step_result.status = StepStatus.NEEDS_ASSET
                        step_result.error = f"素材 '{asset_id}' 未在本地找到，请确认素材已下载"
                        step_result.missing_assets = [missing or asset_id]
                        result.missing_assets.extend(step_result.missing_assets)
                        self._notify(step_result)
                        continue
                elif requires_download:
                    # 需要用户上传素材
                    step_result.status = StepStatus.NEEDS_ASSET
                    step_result.error = f"请上传【{missing or '所需素材'}】后再试"
                    step_result.missing_assets = [missing] if missing else []
                    result.missing_assets.extend(step_result.missing_assets)
                    self._notify(step_result)
                    continue
                # else: asset_id 为 null 且不需要下载，使用 source 文本描述作为降级

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