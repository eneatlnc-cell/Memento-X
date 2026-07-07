"""
Memento-X 工具基类

所有工具的抽象接口。每个工具实现此接口即可被调度器统一调用。

使用方式：
    class MyCropTool(Tool):
        name = "crop"
        description = "画面裁剪"

        def execute(self, params: dict, context: dict) -> dict:
            ...
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class Tool(ABC):
    """
    工具基类。

    每个工具必须实现：
    - name: 工具名称（与工作流中的 action 对应）
    - description: 简短描述
    - execute(): 执行逻辑

    可选：
    - version: 版本号
    - required: 是否必需（FFmpeg 是必需的）
    """

    name: str = ""
    description: str = ""
    version: str = "1.0"
    required: bool = False

    @abstractmethod
    def execute(self, params: dict, context: dict) -> dict:
        """
        执行工具。

        Args:
            params: 工作流中该步骤的 params 字段
            context: 共享上下文，包含：
                - workspace: 工作目录
                - previous_output: 上一步的输出路径
                - assets: 素材库映射表 {asset_id: local_path}
                - step_id: 当前步骤 ID
                - step_index: 当前步骤索引

        Returns:
            dict: {
                "success": True/False,
                "output": "输出文件路径",
                "error": "错误信息（如果失败）",
                "warnings": ["警告信息列表"],
                "metadata": {}  # 可选元数据
            }
        """
        ...

    def can_execute(self) -> bool:
        """
        检查工具是否可用（依赖是否安装）。

        调度器在注册工具时调用，返回 False 的工具会被标记为不可用。
        """
        return True

    def __repr__(self) -> str:
        return f"Tool({self.name}, v{self.version})"


class ToolContext:
    """
    工具执行上下文。

    封装了调度器传递给工具的所有共享信息。
    """

    def __init__(
        self,
        workspace: str,
        previous_output: Optional[str] = None,
        assets: Optional[Dict[str, str]] = None,
        step_id: str = "",
        step_index: int = 0,
    ):
        self.workspace = workspace
        self.previous_output = previous_output
        self.assets = assets or {}
        self.step_id = step_id
        self.step_index = step_index

    def resolve_asset(self, asset_id: Optional[str]) -> Optional[str]:
        """根据 asset_id 解析本地路径"""
        if not asset_id:
            return None
        return self.assets.get(asset_id)

    def to_dict(self) -> dict:
        return {
            "workspace": self.workspace,
            "previous_output": self.previous_output,
            "assets": self.assets,
            "step_id": self.step_id,
            "step_index": self.step_index,
        }


class ToolResult:
    """工具执行结果"""

    def __init__(
        self,
        success: bool = True,
        output: str = "",
        error: str = "",
        warnings: Optional[list] = None,
        metadata: Optional[dict] = None,
    ):
        self.success = success
        self.output = output
        self.error = error
        self.warnings = warnings or []
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }

    @classmethod
    def ok(cls, output: str = "", **kwargs) -> "ToolResult":
        """快速创建成功结果"""
        return cls(success=True, output=output, **kwargs)

    @classmethod
    def fail(cls, error: str = "", **kwargs) -> "ToolResult":
        """快速创建失败结果"""
        return cls(success=False, error=error, **kwargs)