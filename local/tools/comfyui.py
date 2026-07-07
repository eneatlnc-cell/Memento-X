"""
ComfyUI 特效生成工具接口

AI 特效生成（火焰/粒子/光效/替换）
输入：图片/视频 + 效果描述
输出：处理后的帧序列
"""
import os
import subprocess
import json
from typing import Optional


async def execute(
    action: str,
    params: dict,
    workspace: str,
    previous_output: Optional[str] = None,
) -> Optional[str]:
    """
    执行 ComfyUI 特效。

    Args:
        action: 工具动作 (replace / effect)
        params: {"type": "fire"|"particle"|"glow", "prompt": "..."}
        workspace: 工作目录
        previous_output: 上一步的输出

    Returns:
        处理后的帧序列目录
    """
    input_path = params.get("input_path", previous_output)
    effect_type = params.get("type", "particle")
    prompt = params.get("prompt", "")

    output_dir = os.path.join(workspace, "output", f"effect_{effect_type}")
    os.makedirs(output_dir, exist_ok=True)

    # 构造 ComfyUI workflow JSON
    # 实际部署时根据 effect_type 选择不同的 workflow 模板
    workflow = _build_workflow(action, effect_type, input_path, output_dir, prompt)

    workflow_path = os.path.join(workspace, "temp", "workflow.json")
    os.makedirs(os.path.dirname(workflow_path), exist_ok=True)
    with open(workflow_path, "w") as f:
        json.dump(workflow, f)

    cmd = [
        "python", "-m", "comfyui_cli",
        "--workflow", workflow_path,
        "--output", output_dir,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return output_dir
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ComfyUI 特效生成失败: {e.stderr}")


def _build_workflow(action: str, effect_type: str, input_path: str,
                    output_dir: str, prompt: str) -> dict:
    """构造 ComfyUI workflow JSON"""
    # 简化版 workflow 模板
    # 生产环境使用完整的 ComfyUI API 构造 workflow
    return {
        "nodes": [
            {"id": 1, "type": "LoadImage", "inputs": {"image": input_path}},
            {"id": 2, "type": "CLIPTextEncode", "inputs": {"text": prompt or effect_type}},
            {"id": 3, "type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0}},
            {"id": 4, "type": "VAEDecode", "inputs": {}},
            {"id": 5, "type": "SaveImage", "inputs": {"filename_prefix": output_dir}},
        ],
        "links": [[1, 0, 3, 0], [2, 0, 3, 1], [3, 0, 4, 0], [4, 0, 5, 0]],
    }