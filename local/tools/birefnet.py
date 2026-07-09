"""
BiRefNet 工具模块（兼容别名）

从 scene_edit.py 重新导出 execute 函数，保持向后兼容。
"""
from local.tools.scene_edit import execute

__all__ = ["execute"]