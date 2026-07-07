"""
HyperFrames 字幕/标题渲染工具接口

字幕渲染引擎（开源）
输入：文本内容 + 样式
输出：字幕叠加后的视频
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
    执行 HyperFrames 字幕渲染。

    Args:
        action: 工具动作 (subtitle)
        params: {"text": "字幕内容", "style": "bottom"|"karaoke"}
        workspace: 工作目录
        previous_output: 上一步的输出

    Returns:
        字幕叠加后的视频路径
    """
    input_path = previous_output
    text = params.get("text", "")
    style = params.get("style", "bottom")

    output_path = os.path.join(workspace, "output", "subtitled.mp4")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if style == "karaoke":
        # 卡拉 OK 效果：逐字高亮
        drawtext = (
            f"drawtext=text='{text}':fontcolor=white:fontsize=48:"
            f"x=(w-text_w)/2:y=h-th-60:"
            f"box=1:boxcolor=black@0.5:boxborderw=10"
        )
    else:
        # 底部字幕
        drawtext = (
            f"drawtext=text='{text}':fontcolor=white:fontsize=36:"
            f"x=(w-text_w)/2:y=h-th-40:"
            f"bordercolor=black:borderw=2"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", drawtext,
        "-c:a", "copy",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"字幕渲染失败: {e.stderr}")