"""
Memento-X FFmpeg 通用函数

提供 FFmpeg 命令行工具的通用封装，供 crop、composite、export 等工具复用。

特性：
- 统一的 ffmpeg 调用封装
- 分辨率/宽高比/编码格式映射表
- 输出路径构建
- 超时和错误处理
"""
import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

# ── 常量映射表 ──

# 宽高比 → (宽, 高)
ASPECT_RATIO_MAP = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:3": (1440, 1080),
    "21:9": (2560, 1080),
    "3:2": (1620, 1080),
    "2:1": (2160, 1080),
}

# 分辨率 → (宽, 高)
RESOLUTION_MAP = {
    "4k": (3840, 2160),
    "2k": (2560, 1440),
    "1080p": (1920, 1080),
    "720p": (1280, 720),
    "480p": (854, 480),
}

# 编码格式 → (编码器, 文件扩展名, 像素格式)
CODEC_MAP = {
    "h264": ("libx264", "mp4", "yuv420p"),
    "h265": ("libx265", "mp4", "yuv420p"),
    "prores": ("prores_ks", "mov", "yuv422p10le"),
    "prores_4444": ("prores_ks", "mov", "yuva444p10le"),
    "vp9": ("libvpx-vp9", "webm", "yuv420p"),
    "dnxhd": ("dnxhd", "mov", "yuv422p"),
}

# FFmpeg 默认超时（秒）
DEFAULT_TIMEOUT = 1800  # 30 分钟


# ── 公共函数 ──

def run_ffmpeg(
    cmd: List[str],
    timeout: int = DEFAULT_TIMEOUT,
    description: str = "FFmpeg",
) -> str:
    """
    执行 FFmpeg 命令并返回 stdout。

    Args:
        cmd: FFmpeg 命令行参数列表
        timeout: 超时时间（秒）
        description: 操作描述（用于错误信息）

    Returns:
        str: stdout 输出

    Raises:
        RuntimeError: FFmpeg 执行失败
    """
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{description} 超时（{timeout}秒）")
    except subprocess.CalledProcessError as e:
        stderr_tail = e.stderr.strip().split("\n")[-5:] if e.stderr else ["无错误输出"]
        raise RuntimeError(f"{description} 失败: {'; '.join(stderr_tail)}")


def build_output_path(
    workspace: str,
    filename: str,
    format_type: str = "h264",
) -> str:
    """
    构建输出文件路径并确保目录存在。

    Args:
        workspace: 工作目录
        filename: 文件名（不含扩展名）
        format_type: 编码格式（用于确定扩展名）

    Returns:
        str: 完整的输出文件路径
    """
    ext = CODEC_MAP.get(format_type, ("", "mp4", ""))[1]
    output_dir = os.path.join(workspace, "output")
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{filename}.{ext}")


def get_aspect_dimensions(
    aspect: str = "16:9",
    resolution: str = "1080p",
) -> tuple:
    """
    根据宽高比和分辨率获取目标尺寸。

    优先级：显式 resolution > aspect > 默认值

    Args:
        aspect: 宽高比，如 "16:9"
        resolution: 分辨率标签，如 "1080p"

    Returns:
        tuple: (width, height)
    """
    # 如果显式指定了分辨率且不是默认值，优先使用
    if resolution in RESOLUTION_MAP:
        return RESOLUTION_MAP[resolution]
    if aspect in ASPECT_RATIO_MAP:
        return ASPECT_RATIO_MAP[aspect]
    return (1920, 1080)  # 默认 1080p 16:9


def get_codec_params(format_type: str) -> tuple:
    """
    获取编码器参数。

    Args:
        format_type: 编码格式标签

    Returns:
        tuple: (codec, extension, pixel_format)
    """
    return CODEC_MAP.get(format_type, CODEC_MAP["h264"])


def get_scale_filter(resolution: str) -> str:
    """
    获取缩放滤镜字符串。

    Args:
        resolution: 分辨率标签，如 "4k", "1080p"

    Returns:
        str: FFmpeg scale 滤镜参数
    """
    if resolution in RESOLUTION_MAP:
        w, h = RESOLUTION_MAP[resolution]
        return f"scale={w}:{h}"
    if resolution in ASPECT_RATIO_MAP:
        w, h = ASPECT_RATIO_MAP[resolution]
        return f"scale={w}:{h}"
    return "scale=1920:1080"


def get_crop_filter(aspect: str, resolution: str = "1080p") -> str:
    """
    获取裁剪+缩放滤镜字符串。

    按目标宽高比裁剪（居中裁剪），然后缩放到目标分辨率。

    Args:
        aspect: 目标宽高比
        resolution: 目标分辨率标签

    Returns:
        str: FFmpeg crop+scale 滤镜参数
    """
    w, h = get_aspect_dimensions(aspect, resolution)
    return f"crop=ih*{w}/{h}:ih,scale={w}:{h}"


def check_ffmpeg_available() -> bool:
    """
    检查 FFmpeg 是否可用。

    Returns:
        bool: FFmpeg 是否已安装
    """
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_ffmpeg_version() -> Optional[str]:
    """
    获取 FFmpeg 版本信息。

    Returns:
        str | None: 版本字符串
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        first_line = result.stdout.strip().split("\n")[0] if result.stdout else ""
        return first_line
    except Exception:
        return None