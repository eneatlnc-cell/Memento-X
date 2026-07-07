"""
FFmpeg 合成工具接口

视频合成（LGPL）
输入：帧序列目录
输出：4K ProRes / H.264 MP4
"""
import os
import subprocess
from typing import Optional


async def execute(
    action: str,
    params: dict,
    workspace: str,
    previous_output: Optional[str] = None,
) -> Optional[str]:
    """
    执行 FFmpeg 操作。

    Args:
        action: 工具动作 (composite / crop / stabilize / denoise)
        params: 参数
        workspace: 工作目录
        previous_output: 上一步的输出

    Returns:
        输出文件路径
    """
    handlers = {
        "composite": _handle_composite,
        "crop": _handle_crop,
        "stabilize": _handle_stabilize,
        "denoise": _handle_denoise,
    }

    handler = handlers.get(action, _handle_composite)
    return await handler(params, workspace, previous_output)


async def _handle_composite(params: dict, workspace: str, previous_output: Optional[str]) -> str:
    """合成帧序列为视频"""
    input_dir = params.get("input_dir", previous_output)
    format_type = params.get("format", "h264")
    resolution = params.get("resolution", "4k")
    fps = params.get("fps", 24)

    ext = "mp4" if format_type == "h264" else "mov"
    output_path = os.path.join(workspace, "output", f"final.{ext}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    codec = "libx264" if format_type == "h264" else "prores_ks"
    scale = "3840:2160" if resolution == "4k" else "1920:1080"

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", os.path.join(input_dir, "frame_%06d.png") if input_dir else "",
        "-c:v", codec,
        "-vf", f"scale={scale}",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=1800)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg 合成失败: {e.stderr}")


async def _handle_crop(params: dict, workspace: str, previous_output: Optional[str]) -> str:
    """裁剪视频"""
    input_path = previous_output
    aspect = params.get("aspect", "16:9")
    resolution = params.get("resolution", "1080p")

    aspect_map = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
    w, h = aspect_map.get(aspect, (1920, 1080))

    output_path = os.path.join(workspace, "output", f"cropped.mp4")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"crop=ih*{w}/{h}:ih,scale={w}:{h}",
        "-c:a", "copy",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg 裁剪失败: {e.stderr}")


async def _handle_stabilize(params: dict, workspace: str, previous_output: Optional[str]) -> str:
    """视频防抖"""
    input_path = previous_output
    output_path = os.path.join(workspace, "output", "stabilized.mp4")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", "vidstabdetect=shakiness=5:accuracy=15,vidstabtransform=smoothing=10",
        "-c:a", "copy",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=1200)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg 防抖失败: {e.stderr}")


async def _handle_denoise(params: dict, workspace: str, previous_output: Optional[str]) -> str:
    """视频降噪"""
    input_path = previous_output
    strength = params.get("strength", "medium")

    strength_map = {"light": "hqdn3d=4:3:6:4.5", "medium": "hqdn3d=8:6:12:9", "strong": "hqdn3d=16:12:24:18"}
    denoise_filter = strength_map.get(strength, "hqdn3d=8:6:12:9")

    output_path = os.path.join(workspace, "output", "denoised.mp4")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", denoise_filter,
        "-c:a", "copy",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=1200)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg 降噪失败: {e.stderr}")