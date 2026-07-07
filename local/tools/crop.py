"""
Memento-X 裁剪工具

视频/画面裁剪，支持多种宽高比和分辨率。
基于 FFmpeg 实现。

工作流 params:
    aspect: 目标宽高比（16:9, 9:16, 1:1, 4:3, 21:9）
    resolution: 目标分辨率（4k, 1080p, 720p）
    input_path: 输入文件路径（可选，默认从 context 获取）
"""
import logging
from typing import Optional

from local.tools.base import Tool, ToolResult, ToolContext
from local.tools.ffmpeg_utils import (
    run_ffmpeg,
    build_output_path,
    get_crop_filter,
    get_aspect_dimensions,
)

logger = logging.getLogger(__name__)


class CropTool(Tool):
    """视频/画面裁剪工具"""

    name = "crop"
    description = "画面裁剪 — 按宽高比裁剪并缩放到目标分辨率"
    version = "1.0"
    required = True  # FFmpeg 是必需的

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """
        执行裁剪操作。

        Args:
            params:
                aspect: 目标宽高比，默认 "16:9"
                resolution: 目标分辨率，默认 "1080p"
                input_path: 输入文件路径（可选）
            context: 执行上下文

        Returns:
            ToolResult
        """
        input_path = params.get("input_path", context.previous_output)
        if not input_path:
            return ToolResult.fail(error="裁剪缺少输入文件：请提供 input_path 或确保上一步有输出")

        aspect = params.get("aspect", "16:9")
        resolution = params.get("resolution", "1080p")

        output_path = build_output_path(context.workspace, "cropped", "h264")
        crop_filter = get_crop_filter(aspect, resolution)
        w, h = get_aspect_dimensions(aspect, resolution)

        logger.info(f"裁剪: {aspect} → {w}x{h} → {output_path}")

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", crop_filter,
            "-c:a", "copy",
            output_path,
        ]

        try:
            run_ffmpeg(cmd, timeout=600, description=f"裁剪 ({aspect})")
            return ToolResult.ok(
                output=output_path,
                metadata={"aspect": aspect, "resolution": f"{w}x{h}"},
            )
        except RuntimeError as e:
            return ToolResult.fail(error=str(e))

    def can_execute(self) -> bool:
        from local.tools.ffmpeg_utils import check_ffmpeg_available
        return check_ffmpeg_available()


# ── 模块级兼容接口（供旧调度器使用） ──

async def execute(
    action: str,
    params: dict,
    workspace: str,
    previous_output: Optional[str] = None,
) -> Optional[str]:
    """兼容旧接口的 async execute 函数"""
    tool = CropTool()
    context = ToolContext(
        workspace=workspace,
        previous_output=previous_output,
    )
    result = tool.execute(params, context)
    if result.success:
        return result.output
    raise RuntimeError(result.error)