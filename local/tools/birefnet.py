"""
BiRefNet 抠图工具接口

高精度图像抠图（MIT 协议）
输入：图片路径
输出：透明背景 PNG / 遮罩
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
    执行 BiRefNet 抠图。

    Args:
        action: 工具动作 (matting)
        params: 参数 {"target": "person"|"object"|"foreground"}
        workspace: 工作目录
        previous_output: 上一步的输出文件路径

    Returns:
        抠图结果路径
    """
    input_path = params.get("input_path", previous_output)
    if not input_path or not os.path.exists(input_path):
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    output_path = os.path.join(workspace, "output", "matting_result.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    target = params.get("target", "foreground")

    # 调用 BiRefNet（实际部署时指向本地安装路径）
    cmd = [
        "python", "-m", "birefnet",
        "--input", input_path,
        "--output", output_path,
        "--target", target,
        "--model", "general",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"BiRefNet 抠图失败: {e.stderr}")