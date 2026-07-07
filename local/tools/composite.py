"""
Memento-X 合成工具

帧序列合成、视频拼接、多轨合成。
基于 FFmpeg 实现。

工作流 params:
    format: 输出格式（h264, h265, prores, vp9）
    resolution: 输出分辨率（4k, 1080p, 720p）
    fps: 帧率（默认 24）
    input_dir: 帧序列输入目录（可选）
    input_paths: 多个输入文件列表（用于拼接）
    mode: 合成模式（frames: 帧序列合成, concat: 视频拼接, overlay: 叠加合成）
"""
import os
import logging
from typing import Optional, List

from local.tools.base import Tool, ToolResult, ToolContext
from local.tools.ffmpeg_utils import (
    run_ffmpeg,
    build_output_path,
    get_codec_params,
    get_scale_filter,
    check_ffmpeg_available,
)

logger = logging.getLogger(__name__)


class CompositeTool(Tool):
    """视频合成工具"""

    name = "composite"
    description = "视频合成 — 帧序列合成、视频拼接、多轨叠加"
    version = "1.0"
    required = True

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """
        执行合成操作。

        Args:
            params:
                mode: 合成模式（frames / concat / overlay）
                format: 编码格式，默认 "h264"
                resolution: 分辨率，默认 "4k"
                fps: 帧率，默认 24
                input_dir: 帧序列目录（mode=frames）
                input_paths: 输入文件列表（mode=concat/overlay）
                background: 背景视频（mode=overlay）
                overlay: 叠加视频（mode=overlay）
            context: 执行上下文

        Returns:
            ToolResult
        """
        mode = params.get("mode", "frames")
        format_type = params.get("format", "h264")
        resolution = params.get("resolution", "4k")
        fps = params.get("fps", 24)

        handlers = {
            "frames": self._composite_frames,
            "concat": self._composite_concat,
            "overlay": self._composite_overlay,
        }

        handler = handlers.get(mode, self._composite_frames)
        return handler(params, context, format_type, resolution, fps)

    def _composite_frames(
        self, params: dict, context: ToolContext,
        format_type: str, resolution: str, fps: int,
    ) -> ToolResult:
        """帧序列合成"""
        input_dir = params.get("input_dir", context.previous_output)
        if not input_dir:
            return ToolResult.fail(error="合成缺少输入目录：请提供 input_dir 或确保上一步有输出")

        output_path = build_output_path(context.workspace, "composite", format_type)
        codec, ext, pix_fmt = get_codec_params(format_type)
        scale = get_scale_filter(resolution)

        logger.info(f"帧序列合成: {input_dir} → {output_path} ({format_type}, {resolution}, {fps}fps)")

        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", os.path.join(input_dir, "frame_%06d.png"),
            "-c:v", codec,
            "-vf", f"{scale},format={pix_fmt}",
            "-pix_fmt", pix_fmt,
            output_path,
        ]

        try:
            run_ffmpeg(cmd, timeout=1800, description="帧序列合成")
            return ToolResult.ok(
                output=output_path,
                metadata={"format": format_type, "resolution": resolution, "fps": fps},
            )
        except RuntimeError as e:
            return ToolResult.fail(error=str(e))

    def _composite_concat(
        self, params: dict, context: ToolContext,
        format_type: str, resolution: str, fps: int,
    ) -> ToolResult:
        """视频拼接（concat）"""
        input_paths = params.get("input_paths", [])
        if not input_paths:
            # 从 context 获取
            if context.previous_output:
                input_paths = [context.previous_output]
            else:
                return ToolResult.fail(error="拼接缺少输入文件列表")

        output_path = build_output_path(context.workspace, "concatenated", format_type)
        codec, ext, pix_fmt = get_codec_params(format_type)
        scale = get_scale_filter(resolution)

        # 生成 concat 文件列表
        concat_list_path = os.path.join(context.workspace, "temp", "concat_list.txt")
        os.makedirs(os.path.dirname(concat_list_path), exist_ok=True)
        with open(concat_list_path, "w") as f:
            for p in input_paths:
                f.write(f"file '{p}'\n")

        logger.info(f"视频拼接: {len(input_paths)} 个文件 → {output_path}")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c:v", codec,
            "-vf", f"{scale},format={pix_fmt}",
            "-pix_fmt", pix_fmt,
            output_path,
        ]

        try:
            run_ffmpeg(cmd, timeout=1800, description="视频拼接")
            return ToolResult.ok(
                output=output_path,
                metadata={"format": format_type, "resolution": resolution, "input_count": len(input_paths)},
            )
        except RuntimeError as e:
            return ToolResult.fail(error=str(e))

    def _composite_overlay(
        self, params: dict, context: ToolContext,
        format_type: str, resolution: str, fps: int,
    ) -> ToolResult:
        """叠加合成（画中画 / 多轨叠加）"""
        background = params.get("background", context.previous_output)
        overlay = params.get("overlay", "")
        position = params.get("position", "center")  # center, top-left, bottom-right, etc.

        if not background:
            return ToolResult.fail(error="叠加合成缺少背景视频")
        if not overlay:
            return ToolResult.fail(error="叠加合成缺少叠加视频")

        output_path = build_output_path(context.workspace, "overlay", format_type)
        codec, ext, pix_fmt = get_codec_params(format_type)

        # 位置映射
        position_map = {
            "center": "overlay=(W-w)/2:(H-h)/2",
            "top-left": "overlay=10:10",
            "top-right": "overlay=W-w-10:10",
            "bottom-left": "overlay=10:H-h-10",
            "bottom-right": "overlay=W-w-10:H-h-10",
        }
        overlay_filter = position_map.get(position, position_map["center"])

        logger.info(f"叠加合成: bg={background} + overlay={overlay} → {output_path}")

        cmd = [
            "ffmpeg", "-y",
            "-i", background,
            "-i", overlay,
            "-filter_complex", overlay_filter,
            "-c:v", codec,
            "-pix_fmt", pix_fmt,
            output_path,
        ]

        try:
            run_ffmpeg(cmd, timeout=600, description="叠加合成")
            return ToolResult.ok(
                output=output_path,
                metadata={"position": position, "format": format_type},
            )
        except RuntimeError as e:
            return ToolResult.fail(error=str(e))

    def can_execute(self) -> bool:
        return check_ffmpeg_available()


# ── 模块级兼容接口 ──

async def execute(
    action: str,
    params: dict,
    workspace: str,
    previous_output: Optional[str] = None,
) -> Optional[str]:
    """兼容旧接口的 async execute 函数"""
    tool = CompositeTool()
    context = ToolContext(
        workspace=workspace,
        previous_output=previous_output,
    )
    result = tool.execute(params, context)
    if result.success:
        return result.output
    raise RuntimeError(result.error)