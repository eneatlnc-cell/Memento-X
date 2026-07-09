"""
Memento-X 导出工具

视频导出，支持多种格式、分辨率、帧率、码率控制。
基于 FFmpeg 实现。

工作流 params:
    format: 输出格式（h264, h265, prores, prores_4444, vp9, dnxhd）
    resolution: 分辨率（4k, 2k, 1080p, 720p）
    fps: 帧率（24, 30, 60）
    bitrate: 码率控制（CBR: "50M", VBR: "auto"）
    quality: 质量等级（high, medium, low → CRF 值）
    audio: 是否包含音频（默认 true）
    preset: 编码预设（fast, medium, slow）
    output_name: 自定义输出文件名
"""
import logging
from typing import Optional

from local.tools.base import Tool, ToolResult, ToolContext
from local.tools.ffmpeg_utils import (
    run_ffmpeg,
    build_output_path,
    get_codec_params,
    get_scale_filter,
    check_ffmpeg_available,
)

logger = logging.getLogger(__name__)


# ── 编码预设 ──

# CRF 质量映射
QUALITY_CRF = {
    "high": 18,      # 视觉无损
    "medium": 23,    # 标准质量
    "low": 28,       # 压缩优先
}

# 编码预设
ENCODE_PRESETS = {
    "fast": "fast",
    "medium": "medium",
    "slow": "slow",
    "veryslow": "veryslow",
}


class ExportTool(Tool):
    """视频导出工具"""

    name = "export"
    description = "视频导出 — 渲染最终视频，支持多格式/分辨率/码率控制"
    version = "1.0"
    required = True

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """
        执行导出操作。

        Args:
            params:
                format: 编码格式，默认 "h264"
                resolution: 分辨率，默认 "1080p"
                fps: 帧率，默认 24
                bitrate: 码率控制
                quality: 质量等级（high/medium/low）
                audio: 是否包含音频
                preset: 编码预设
                output_name: 自定义文件名
            context: 执行上下文

        Returns:
            ToolResult
        """
        input_path = params.get("input_path", context.previous_output)
        if not input_path:
            return ToolResult.fail(error="导出缺少输入文件：请提供 input_path 或确保上一步有输出")

        format_type = params.get("format", "h264")
        resolution = params.get("resolution", "1080p")
        fps = params.get("fps", 24)
        quality = params.get("quality", "medium")
        audio = params.get("audio", True)
        preset = params.get("preset", "medium")
        output_name = params.get("output_name", "export")

        output_path = build_output_path(context.workspace, output_name, format_type)
        codec, ext, pix_fmt = get_codec_params(format_type)
        scale = get_scale_filter(resolution)
        crf = QUALITY_CRF.get(quality, 23)
        encode_preset = ENCODE_PRESETS.get(preset, "medium")

        logger.info(
            f"导出: {input_path} → {output_path} "
            f"({format_type}, {resolution}, {fps}fps, quality={quality}, preset={preset})"
        )

        # 构建 FFmpeg 命令
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-c:v", codec,
            "-vf", f"{scale},format={pix_fmt}",
            "-pix_fmt", pix_fmt,
            "-r", str(fps),
            "-preset", encode_preset,
            "-crf", str(crf),
        ]

        # 音频处理
        if audio:
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.extend(["-an"])  # 无音频

        # 码率控制（可选）
        bitrate = params.get("bitrate", "")
        if bitrate and bitrate != "auto":
            cmd.extend(["-b:v", bitrate])

        # H.264/265 特定选项
        if format_type in ("h264", "h265"):
            if pix_fmt == "yuv420p":
                pass  # 默认

        cmd.append(output_path)

        try:
            run_ffmpeg(cmd, timeout=3600, description=f"导出 ({format_type}/{resolution})")
            return ToolResult.ok(
                output=output_path,
                metadata={
                    "format": format_type,
                    "resolution": resolution,
                    "fps": fps,
                    "quality": quality,
                    "preset": preset,
                    "codec": codec,
                },
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
    tool = ExportTool()
    context = ToolContext(
        workspace=workspace,
        previous_output=previous_output,
    )
    result = tool.execute(params, context)
    if result.success:
        return result.output
    raise RuntimeError(result.error)