"""
Memento-X 工具注册表

管理所有可用工具的注册、发现和调用。
```
调度器通过 ToolRegistry 查找工具 → 调用 tool.execute(params, context)
```
"""
import importlib
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Type

from local.tools.base import Tool, ToolResult, ToolContext

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """工具未注册"""
    def __init__(self, tool_name: str):
        super().__init__(f"工具未注册: '{tool_name}'")


class ToolRegistry:
    """
    工具注册表。

    支持两种注册方式：
    1. 手动注册：registry.register("crop", CropTool())
    2. 自动发现：registry.discover("local/tools/") 扫描目录加载
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._aliases: Dict[str, str] = {}  # 别名 → 正式名

    # ── 注册 ──

    def register(self, tool: Tool):
        """
        注册工具。

        Args:
            tool: 工具实例
        """
        if not tool.name:
            raise ValueError("工具必须有 name 属性")

        self._tools[tool.name] = tool
        logger.debug(f"工具已注册: {tool}")

    def register_alias(self, alias: str, target: str):
        """
        注册别名（多个 action 映射到同一工具）。

        例如："color_grade" 和 "color" 都映射到 ColorTool
        """
        self._aliases[alias] = target

    def register_many(self, tools: list):
        """批量注册"""
        for t in tools:
            self.register(t)

    # ── 查询 ──

    def get(self, name: str) -> Optional[Tool]:
        """
        获取工具。

        Args:
            name: 工具名称或别名

        Returns:
            Tool | None
        """
        # 先查别名
        resolved = self._aliases.get(name, name)
        return self._tools.get(resolved)

    def get_required(self, name: str) -> Tool:
        """
        获取工具（不存在时抛异常）。

        Raises:
            ToolNotFoundError
        """
        tool = self.get(name)
        if not tool:
            raise ToolNotFoundError(name)
        return tool

    def has(self, name: str) -> bool:
        """检查工具是否已注册"""
        return self.get(name) is not None

    def list_all(self) -> list:
        """列出所有已注册工具"""
        return [{"name": t.name, "description": t.description, "version": t.version}
                for t in self._tools.values()]

    def list_names(self) -> list:
        """列出所有工具名称"""
        return list(self._tools.keys())

    def count(self) -> int:
        return len(self._tools)

    # ── 执行 ──

    def execute(self, action: str, params: dict, context: ToolContext) -> ToolResult:
        """
        执行工具调用。

        Args:
            action: 工具名称
            params: 步骤参数
            context: 执行上下文

        Returns:
            ToolResult: 执行结果

        Raises:
            ToolNotFoundError: 工具未注册
        """
        tool = self.get_required(action)
        logger.info(f"执行工具: {tool.name} (step: {context.step_id})")
        return tool.execute(params, context)

    # ── 自动发现 ──

    def discover(self, tools_dir: str = "local/tools/"):
        """
        扫描目录，自动加载所有工具模块。

        每个模块应导出一个 class 继承 Tool，或一个 execute() 函数。

        自动发现策略：
        1. 查找 *_tool.py 或 tool_*.py 文件
        2. 查找继承 Tool 的类
        3. 查找模块级别的 execute() 函数 → 包装为 FunctionTool

        Args:
            tools_dir: 工具目录路径
        """
        tools_path = Path(tools_dir)
        if not tools_path.exists():
            logger.warning(f"工具目录不存在: {tools_dir}")
            return

        for pyfile in tools_path.glob("*.py"):
            if pyfile.name.startswith("_"):
                continue
            if pyfile.name in ("base.py", "ffmpeg_utils.py", "__init__.py"):
                continue

            module_name = pyfile.stem
            try:
                self._load_module(module_name, pyfile)
            except Exception as e:
                logger.warning(f"加载工具模块失败 {module_name}: {e}")

    def _load_module(self, module_name: str, pyfile: Path):
        """加载单个工具模块"""
        # 动态导入
        spec = importlib.util.spec_from_file_location(
            f"local.tools.{module_name}", str(pyfile)
        )
        if not spec or not spec.loader:
            return

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 查找 Tool 子类
        tool_found = False
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, Tool) and attr is not Tool:
                self.register(attr())
                tool_found = True

        # 查找 execute() 函数 → 包装为 FunctionTool
        if not tool_found and hasattr(module, "execute"):
            self.register(FunctionTool(module_name, module.execute))

        logger.info(f"工具模块已加载: {module_name} ({'class' if tool_found else 'function'})")


class FunctionTool(Tool):
    """
    函数式工具包装器。

    将模块级别的 execute() 函数包装为 Tool 接口。
    兼容已有的工具模块（birefnet.py, sam2.py 等）。
    """

    def __init__(self, name: str, func):
        self.name = name
        self.description = f"FunctionTool wrapper for {name}"
        self._func = func

    def execute(self, params: dict, context: dict) -> dict:
        """
        调用底层的 execute() 函数。

        适配新老接口：老接口用 (action, params, workspace, previous_output)，
        新接口用 (params, context: ToolContext)。

        自动处理 async 函数（旧工具模块的 execute 均为 async def）。
        """
        import inspect
        import asyncio

        sig = inspect.signature(self._func)
        param_names = list(sig.parameters.keys())
        is_async = inspect.iscoroutinefunction(self._func)

        def _run(result_or_coro):
            """如果是协程，用 asyncio.run 执行"""
            if is_async or inspect.iscoroutine(result_or_coro):
                return asyncio.run(result_or_coro) if inspect.iscoroutine(result_or_coro) else asyncio.run(result_or_coro)
            return result_or_coro

        if len(param_names) >= 4 and "action" in param_names:
            # 老接口: execute(action, params, workspace, previous_output)
            call_result = self._func(
                action=self.name,
                params=params,
                workspace=context.workspace,
                previous_output=context.previous_output,
            )
            result = _run(call_result)
            if isinstance(result, str) or result is None:
                return ToolResult.ok(output=result or "")
            return ToolResult(**result) if isinstance(result, dict) else ToolResult.ok(output=str(result))
        else:
            # 新接口: execute(params, context)
            call_result = self._func(params, context)
            result = _run(call_result)
            if isinstance(result, ToolResult):
                return result
            if isinstance(result, dict):
                return ToolResult(**result)
            return ToolResult.ok(output=str(result) if result else "")


# ── 全局注册表 ──
registry = ToolRegistry()