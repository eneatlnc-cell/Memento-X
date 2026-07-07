"""
DaVinci Resolve API 调色工具接口

专业调色（需用户自行安装 DaVinci Resolve）
"""
import os
from typing import Optional


async def execute(
    action: str,
    params: dict,
    workspace: str,
    previous_output: Optional[str] = None,
) -> Optional[str]:
    """
    执行 DaVinci Resolve 调色。

    注意：DaVinci Resolve 需要用户自行安装。
    如果未安装，此步骤将被跳过。
    """
    # 检查 DaVinci 是否可用
    if not _check_davinci_available():
        print("DaVinci Resolve 未安装，跳过调色步骤")
        return previous_output  # 不修改，直接透传

    input_path = params.get("input_path", previous_output)
    style = params.get("style", "cinematic")

    output_path = os.path.join(workspace, "output", "graded.mp4")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 通过 DaVinci Resolve scripting API 调色
    # 实际部署时使用 Resolve API Python 绑定
    # import DaVinciResolveScript as dvr

    # 简化实现：使用 FFmpeg 做基础调色（作为 DaVinci 不可用时的 fallback）
    import subprocess

    lut_map = {
        "cinematic": "colorbalance=rs=0.1:gs=-0.1:bs=0.1,eq=contrast=1.1:saturation=1.1",
        "warm": "colorbalance=rs=0.2:gs=0.0:bs=-0.1,eq=saturation=1.05",
        "cool": "colorbalance=rs=-0.1:gs=0.0:bs=0.2,eq=saturation=1.05",
        "vintage": "colorbalance=rs=0.15:gs=0.05:bs=-0.1,eq=contrast=0.95:saturation=0.8",
    }

    lut = lut_map.get(style, lut_map["cinematic"])

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", lut,
        "-c:a", "copy",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"调色失败: {e.stderr}")


def _check_davinci_available() -> bool:
    """检查 DaVinci Resolve 是否可用"""
    import platform
    system = platform.system()
    paths = {
        "Darwin": "/Applications/DaVinci Resolve/",
        "Windows": "C:\\Program Files\\Blackmagic Design\\DaVinci Resolve\\",
        "Linux": "/opt/resolve/",
    }
    return os.path.exists(paths.get(system, ""))