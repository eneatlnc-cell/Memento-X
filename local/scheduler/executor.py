"""
Memento-X 工作流调度器（WorkflowExecutor）

接收云端 JSON 工作流，解析依赖关系，按 DAG 拓扑顺序执行工具调用。

核心链路：
工作流JSON → 解析步骤 → 构建DAG → 拓扑排序 → 并行分组 → 执行工具 → 返回结果

特性：
- DAG 依赖解析 + 循环检测
- 同层步骤并行执行（concurrent.futures）
- 资产引用解析（asset_id → 本地路径）
- fallback 降级支持
- 单步失败不中断整体流程（可配置）
- 实时状态回传
- 完整执行日志
"""
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

from local.scheduler.asset_resolver import AssetResolver, AssetNotFoundError
from local.scheduler.dag import (
    build_execution_plan,
    get_dependent_steps,
    MissingDependencyError,
    CycleDetectedError,
)
from local.scheduler.tool_registry import ToolRegistry, ToolNotFoundError
from local.tools.base import ToolContext, ToolResult

logger = logging.getLogger(__name__)


# ── 执行状态枚举 ──

class ExecutionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NEEDS_ASSET = "needs_asset"


# ── 步骤执行结果 ──

class StepExecutionResult:
    """单个步骤的执行结果"""

    def __init__(
        self,
        step_id: str = "",
        status: ExecutionStatus = ExecutionStatus.PENDING,
        output: str = "",
        error: str = "",
        duration_ms: int = 0,
        missing_assets: Optional[List[str]] = None,
    ):
        self.step_id = step_id
        self.status = status
        self.output = output
        self.error = error
        self.duration_ms = duration_ms
        self.missing_assets = missing_assets or []

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "missing_assets": self.missing_assets,
        }


# ── 主调度器 ──

class WorkflowExecutor:
    """
    工作流执行器。

    使用方式：
        executor = WorkflowExecutor(tools_dir="local/tools/", assets_dir="~/.memento/assets")
        result = executor.execute(workflow_json)
        # result: {"status": "success", "results": {...}, "errors": {...}}
    """

    def __init__(
        self,
        tools_dir: str = "local/tools/",
        assets_dir: Optional[str] = None,
        workspace: str = "~/.memento/workspace",
    ):
        """
        初始化调度器。

        Args:
            tools_dir: 工具目录路径
            assets_dir: 本地素材库根目录（用于解析 asset_id → 文件路径）
            workspace: 工作目录（中间文件、输出文件存放位置）
        """
        self.workspace = os.path.expanduser(workspace)
        self.tools_dir = tools_dir
        self.assets_dir = assets_dir

        # 工具注册表
        self.registry = ToolRegistry()
        self._init_tools()

        # 资产解析器
        self.asset_resolver = AssetResolver(assets_dir) if assets_dir else None

        # 回调
        self._on_step_update: Optional[Callable[[StepExecutionResult], None]] = None

        # 配置
        self.stop_on_error = False  # True: 单步失败立即中断；False: 继续执行独立步骤

        logger.info(
            f"WorkflowExecutor 初始化完成 "
            f"(tools: {self.registry.count()}, assets: {self.asset_resolver is not None})"
        )

    def _init_tools(self):
        """初始化工具注册表"""
        # 先尝试自动发现
        self.registry.discover(self.tools_dir)

        # 注册别名（多个 action 映射到同一工具）
        # 工作流 action → 实际工具模块名
        # 注意：如果工具已直接注册（如 crop, composite, export），则不需要别名
        _direct_tools = set(self.registry.list_names())
        _aliases = {
            "scene_edit": "birefnet",
            "track": "sam2",
            "replace": "comfyui",
            "effect": "comfyui",
            "render": "ffmpeg",
            "stabilize": "ffmpeg",
            "denoise": "ffmpeg",
            "color": "ffmpeg",
            "color_grade": "davinci",
            "subtitle": "hyperframes",
        }
        for alias, target in _aliases.items():
            if alias not in _direct_tools:
                self.registry.register_alias(alias, target)

        # 如果自动发现没有加载到工具，手动注册 fallback
        if self.registry.count() == 0:
            self._register_fallback_tools()

    def _register_fallback_tools(self):
        """手动注册内置工具（自动发现失败时的 fallback）"""
        try:
            from local.tools import (
                birefnet, sam2, comfyui, ffmpeg, davinci, hyperframes,
            )
            from local.scheduler.tool_registry import FunctionTool

            fallback_tools = [
                ("birefnet", birefnet.execute),
                ("sam2", sam2.execute),
                ("comfyui", comfyui.execute),
                ("ffmpeg", ffmpeg.execute),
                ("davinci", davinci.execute),
                ("hyperframes", hyperframes.execute),
            ]

            for name, func in fallback_tools:
                self.registry.register(FunctionTool(name, func))

            logger.info(f"手动注册了 {len(fallback_tools)} 个 fallback 工具")
        except ImportError as e:
            logger.warning(f"无法加载 fallback 工具: {e}")

    # ── 公共 API ──

    def on_step_update(self, callback: Callable[[StepExecutionResult], None]):
        """注册步骤状态更新回调（用于 UI 进度显示）"""
        self._on_step_update = callback

    def execute(self, workflow: dict) -> dict:
        """
        执行工作流 JSON。

        Args:
            workflow: 符合 schema/workflow.json 的工作流 JSON

        Returns:
            dict: {
                "status": "success" | "failed" | "partial",
                "results": {step_id: output_path},
                "errors": {step_id: error_message},
                "steps": [StepExecutionResult.to_dict(), ...],
                "total_duration_ms": int,
            }
        """
        steps = workflow.get("steps", [])
        if not steps:
            return {
                "status": "failed",
                "results": {},
                "errors": {"_workflow": "工作流为空"},
                "steps": [],
                "total_duration_ms": 0,
            }

        workflow_start = time.time()

        # ── 1. 构建执行计划 ──
        try:
            groups = build_execution_plan(steps)
        except MissingDependencyError as e:
            return {
                "status": "failed",
                "results": {},
                "errors": {"_dag": str(e)},
                "steps": [],
                "total_duration_ms": int((time.time() - workflow_start) * 1000),
            }
        except CycleDetectedError as e:
            return {
                "status": "failed",
                "results": {},
                "errors": {"_dag": str(e)},
                "steps": [],
                "total_duration_ms": int((time.time() - workflow_start) * 1000),
            }

        # ── 2. 构建步骤查找表 ──
        step_map: Dict[str, dict] = {s["id"]: s for s in steps}

        # ── 3. 执行 ──
        results: Dict[str, str] = {}       # step_id → output_path
        errors: Dict[str, str] = {}         # step_id → error_message
        step_outputs: Dict[str, str] = {}   # step_id → output_path (for dependency resolution)
        failed_steps: set = set()           # 失败步骤集合
        step_results: List[StepExecutionResult] = []

        logger.info(f"开始执行工作流: {len(steps)} 步, {len(groups)} 个并行组")

        for group_idx, group in enumerate(groups):
            logger.debug(f"执行组 {group_idx + 1}/{len(groups)}: {group}")

            # 过滤出需要执行的步骤（跳过依赖失败的步骤）
            executable_steps = []
            for step_id in group:
                step = step_map[step_id]
                deps = step.get("depends_on", [])

                # 检查依赖是否全部成功
                dep_failed = [d for d in deps if d in failed_steps]
                if dep_failed:
                    sr = StepExecutionResult(
                        step_id=step_id,
                        status=ExecutionStatus.SKIPPED,
                        error=f"依赖步骤失败: {dep_failed}",
                    )
                    errors[step_id] = sr.error
                    failed_steps.add(step_id)
                    step_results.append(sr)
                    self._notify(sr)
                    continue

                executable_steps.append(step_id)

            if not executable_steps:
                continue

            # ── 并行执行同组步骤 ──
            if self.stop_on_error:
                # stop_on_error 模式：顺序执行，失败立即中止
                for step_id in executable_steps:
                    step = step_map[step_id]
                    sr = self._execute_single_step(step, step_map, step_outputs, errors)
                    step_results.append(sr)

                    if sr.status == ExecutionStatus.COMPLETED:
                        results[step_id] = sr.output
                        step_outputs[step_id] = sr.output
                    else:
                        errors[step_id] = sr.error
                        failed_steps.add(step_id)
                        dependent_ids = get_dependent_steps(steps, step_id)
                        for dep_id in dependent_ids:
                            if dep_id not in failed_steps:
                                failed_steps.add(dep_id)
                        self._skip_remaining(step_map, groups, group_idx, failed_steps, step_results, errors)
                        break

                if failed_steps:
                    break
            elif len(executable_steps) == 1:
                # 单步骤：直接执行，避免线程池开销
                step_id = executable_steps[0]
                step = step_map[step_id]
                sr = self._execute_single_step(step, step_map, step_outputs, errors)
                step_results.append(sr)

                if sr.status == ExecutionStatus.COMPLETED:
                    results[step_id] = sr.output
                    step_outputs[step_id] = sr.output
                else:
                    errors[step_id] = sr.error
                    failed_steps.add(step_id)
                    dependent_ids = get_dependent_steps(steps, step_id)
                    for dep_id in dependent_ids:
                        if dep_id not in failed_steps:
                            failed_steps.add(dep_id)
            else:
                # 多步骤：并行执行
                with ThreadPoolExecutor(max_workers=len(executable_steps)) as pool:
                    futures = {}
                    for step_id in executable_steps:
                        step = step_map[step_id]
                        future = pool.submit(
                            self._execute_single_step,
                            step, step_map, step_outputs, errors,
                        )
                        futures[future] = step_id

                    for future in as_completed(futures):
                        step_id = futures[future]
                        try:
                            sr = future.result()
                        except Exception as e:
                            sr = StepExecutionResult(
                                step_id=step_id,
                                status=ExecutionStatus.FAILED,
                                error=f"执行异常: {e}",
                            )

                        step_results.append(sr)

                        if sr.status == ExecutionStatus.COMPLETED:
                            results[step_id] = sr.output
                            step_outputs[step_id] = sr.output
                        else:
                            errors[step_id] = sr.error
                            failed_steps.add(step_id)
                            dependent_ids = get_dependent_steps(steps, step_id)
                            for dep_id in dependent_ids:
                                if dep_id not in failed_steps:
                                    failed_steps.add(dep_id)

        # ── 4. 汇总结果 ──
        total_duration = int((time.time() - workflow_start) * 1000)

        if not errors:
            status = "success"
        elif not results:
            status = "failed"
        else:
            status = "partial"

        logger.info(
            f"工作流执行完成: status={status}, "
            f"success={len(results)}, failed={len(errors)}, "
            f"duration={total_duration}ms"
        )

        return {
            "status": status,
            "results": results,
            "errors": errors,
            "steps": [s.to_dict() for s in step_results],
            "total_duration_ms": total_duration,
        }

    # ── 单步执行 ──

    def _execute_single_step(
        self,
        step: dict,
        step_map: Dict[str, dict],
        step_outputs: Dict[str, str],
        errors: Dict[str, str],
    ) -> StepExecutionResult:
        """
        执行单个步骤。

        流程：
        1. 资产解析（asset_id → 本地路径）
        2. 构建 ToolContext
        3. 调用工具
        4. 处理结果（含 fallback）
        """
        step_id = step["id"]
        action = step.get("action", "")
        params = dict(step.get("params", {}))  # 复制，避免修改原始数据
        deps = step.get("depends_on", [])

        # ── 资产解析 ──
        sr = self._resolve_assets_for_step(step_id, action, params)
        if sr:
            self._notify(sr)
            return sr

        # ── 构建上下文 ──
        dep_outputs = {d: step_outputs.get(d) for d in deps}
        previous_output = step_outputs.get(deps[-1]) if deps else None

        context = ToolContext(
            workspace=self.workspace,
            previous_output=previous_output,
            assets=dep_outputs,  # 依赖步骤的输出
            step_id=step_id,
            step_index=0,
        )

        # ── 查找工具 ──
        try:
            tool = self.registry.get_required(action)
        except ToolNotFoundError as e:
            # 尝试 fallback
            fallback_sr = self._try_fallback(step, step_map, step_outputs, errors)
            if fallback_sr:
                return fallback_sr

            sr = StepExecutionResult(
                step_id=step_id,
                status=ExecutionStatus.SKIPPED,
                error=str(e),
            )
            self._notify(sr)
            return sr

        # ── 执行 ──
        sr = StepExecutionResult(step_id=step_id, status=ExecutionStatus.RUNNING)
        self._notify(sr)

        t0 = time.time()

        try:
            result = tool.execute(params, context)
            duration = int((time.time() - t0) * 1000)

            if isinstance(result, ToolResult):
                if result.success:
                    return StepExecutionResult(
                        step_id=step_id,
                        status=ExecutionStatus.COMPLETED,
                        output=result.output,
                        duration_ms=duration,
                    )
                else:
                    # 尝试 fallback
                    fallback_sr = self._try_fallback(step, step_map, step_outputs, errors)
                    if fallback_sr:
                        return fallback_sr
                    return StepExecutionResult(
                        step_id=step_id,
                        status=ExecutionStatus.FAILED,
                        error=result.error,
                        duration_ms=duration,
                    )
            elif isinstance(result, dict):
                if result.get("success", True):
                    return StepExecutionResult(
                        step_id=step_id,
                        status=ExecutionStatus.COMPLETED,
                        output=result.get("output", ""),
                        duration_ms=duration,
                    )
                else:
                    fallback_sr = self._try_fallback(step, step_map, step_outputs, errors)
                    if fallback_sr:
                        return fallback_sr
                    return StepExecutionResult(
                        step_id=step_id,
                        status=ExecutionStatus.FAILED,
                        error=result.get("error", "未知错误"),
                        duration_ms=duration,
                    )
            else:
                return StepExecutionResult(
                    step_id=step_id,
                    status=ExecutionStatus.COMPLETED,
                    output=str(result) if result else "",
                    duration_ms=duration,
                )

        except Exception as e:
            duration = int((time.time() - t0) * 1000)
            logger.exception(f"步骤 {step_id} 执行异常: {e}")

            fallback_sr = self._try_fallback(step, step_map, step_outputs, errors)
            if fallback_sr:
                return fallback_sr

            return StepExecutionResult(
                step_id=step_id,
                status=ExecutionStatus.FAILED,
                error=str(e),
                duration_ms=duration,
            )

    # ── 资产解析 ──

    def _resolve_assets_for_step(
        self, step_id: str, action: str, params: dict
    ) -> Optional[StepExecutionResult]:
        """
        解析步骤中的 asset_id 引用为本地文件路径。

        目前主要处理 replace 步骤的 asset_id，
        未来可扩展其他步骤的资产引用。
        """
        if action not in ("replace", "scene_edit"):
            return None

        asset_id = params.get("asset_id")
        if not asset_id:
            # 无 asset_id，检查是否需要下载
            requires_download = params.get("requires_download", False)
            if requires_download:
                missing = params.get("missing_asset", "所需素材")
                return StepExecutionResult(
                    step_id=step_id,
                    status=ExecutionStatus.NEEDS_ASSET,
                    error=f"请上传【{missing}】后再试",
                    missing_assets=[missing],
                )
            return None

        # 有 asset_id，解析为本地路径
        if self.asset_resolver:
            try:
                local_path = self.asset_resolver.resolve(asset_id)
                params["reference_image"] = local_path
                params["input_path"] = local_path
                logger.debug(f"资产已解析: {asset_id} → {local_path}")
                return None
            except AssetNotFoundError:
                return StepExecutionResult(
                    step_id=step_id,
                    status=ExecutionStatus.NEEDS_ASSET,
                    error=f"素材 '{asset_id}' 未在本地找到，请确认素材已下载",
                    missing_assets=[params.get("missing_asset", asset_id)],
                )
        else:
            # 无资产解析器，使用 asset_id 作为路径（fallback）
            potential_path = os.path.join(self.workspace, "assets", asset_id)
            if os.path.exists(potential_path):
                params["reference_image"] = potential_path
                params["input_path"] = potential_path
                return None
            return StepExecutionResult(
                step_id=step_id,
                status=ExecutionStatus.NEEDS_ASSET,
                error=f"素材 '{asset_id}' 未找到，且未配置素材库目录",
                missing_assets=[asset_id],
            )

    def _resolve_asset_path(self, asset_id: Optional[str]) -> Optional[str]:
        """
        根据 asset_id 查找本地素材路径（兼容旧接口）。

        Args:
            asset_id: 素材库中的唯一标识符

        Returns:
            str | None: 本地文件绝对路径

        Raises:
            AssetNotFoundError: 如果 asset_id 不存在于本地素材库
        """
        if not asset_id:
            return None
        if self.asset_resolver:
            return self.asset_resolver.resolve(asset_id)
        return None

    # ── Fallback 处理 ──

    def _try_fallback(
        self,
        step: dict,
        step_map: Dict[str, dict],
        step_outputs: Dict[str, str],
        errors: Dict[str, str],
    ) -> Optional[StepExecutionResult]:
        """
        尝试执行 fallback 降级方案。

        如果步骤定义了 fallback.action，则尝试执行它。
        """
        fallback = step.get("fallback")
        if not fallback:
            return None

        fallback_action = fallback.get("action", "")
        if not fallback_action:
            return None

        logger.info(f"步骤 {step['id']} 失败，尝试 fallback: {fallback_action}")

        fallback_step = {
            "id": f"{step['id']}_fallback",
            "action": fallback_action,
            "params": fallback.get("params", {}),
            "depends_on": step.get("depends_on", []),
        }

        return self._execute_single_step(fallback_step, step_map, step_outputs, errors)

    # ── 跳过处理 ──

    def _skip_remaining(
        self,
        step_map: Dict[str, dict],
        groups: List[List[str]],
        current_group_idx: int,
        failed_steps: set,
        step_results: List[StepExecutionResult],
        errors: Dict[str, str],
    ):
        """将剩余未执行步骤标记为跳过（包括当前组内未执行的步骤）"""
        # 当前组内剩余步骤
        current_group = groups[current_group_idx]
        for step_id in current_group:
            if step_id not in errors and step_id not in [s.step_id for s in step_results]:
                sr = StepExecutionResult(
                    step_id=step_id,
                    status=ExecutionStatus.SKIPPED,
                    error="前置步骤失败，流程已中断",
                )
                errors[step_id] = sr.error
                step_results.append(sr)
                self._notify(sr)

        # 后续所有组
        for group in groups[current_group_idx + 1:]:
            for step_id in group:
                if step_id not in errors and step_id not in [s.step_id for s in step_results]:
                    sr = StepExecutionResult(
                        step_id=step_id,
                        status=ExecutionStatus.SKIPPED,
                        error="前置步骤失败，流程已中断",
                    )
                    errors[step_id] = sr.error
                    step_results.append(sr)
                    self._notify(sr)

    # ── 回调 ──

    def _notify(self, step_result: StepExecutionResult):
        """通知步骤状态变更"""
        if self._on_step_update:
            try:
                self._on_step_update(step_result)
            except Exception:
                logger.warning(f"步骤状态回调异常: {step_result.step_id}", exc_info=True)


# ── 全局单例 ──
executor = WorkflowExecutor()