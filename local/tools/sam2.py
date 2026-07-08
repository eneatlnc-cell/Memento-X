"""
SAM2-MLX 视频遮罩追踪工具接口

视频帧级遮罩追踪（Apache 2.0）
输入：视频路径 + 初始遮罩
输出：24fps 遮罩序列
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
    执行 SAM2 遮罩追踪。

    Args:
        action: 工具动作 (tracking)
        params: {"target": "mask", "fps": 24, "input_video": "..."}
        workspace: 工作目录
        previous_output: 上一步的输出（遮罩/场景编辑结果）

    Returns:
        遮罩序列输出目录
    """
    input_video = params.get("input_video", "")
    mask_input = params.get("mask_input", previous_output)
    fps = params.get("fps", 24)

    output_dir = os.path.join(workspace, "output", "masks")
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "python", "-m", "sam2_tracking",
        "--video", input_video,
        "--mask", mask_input,
        "--output", output_dir,
        "--fps", str(fps),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return output_dir
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"SAM2 追踪失败: {e.stderr}")