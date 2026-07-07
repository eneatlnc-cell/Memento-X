"""
Memento-X 工作流 Schema — Pydantic 模型

定义从云端 AI 意图理解到本地调度器执行的标准化 JSON 指令格式。
与 schema/workflow.json v1.0 保持一致。
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ── 工作流步骤 ──

class WorkflowStep(BaseModel):
    """工作流中的单个步骤"""
    id: str = Field(..., description="步骤唯一标识，如 step_1、matting_person")
    action: str = Field(
        ...,
        description="工具名称，必须是10种工具之一",
        pattern="^(matting|track|replace|composite|effect|color|subtitle|render|crop|export)$",
    )
    target: str = Field(
        default="all",
        description="操作目标: person/background/object/foreground/scene/all/mask/region",
    )
    params: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    depends_on: List[str] = Field(default_factory=list, description="依赖的前置步骤 ID 列表")
    fallback: Optional[Dict[str, Any]] = Field(default=None, description="失败时的降级方案")
    reason: str = Field(default="", description="为什么需要这一步")


# ── 工作流 ──

class Workflow(BaseModel):
    """完整工作流"""
    version: str = Field(default="1.0", description="Schema 版本号")
    workflow_id: str = Field(..., description="工作流唯一标识 (UUID v4)")
    understood: str = Field(default="", description="AI 对用户意图的理解摘要")
    created_at: Optional[str] = Field(default=None, description="创建时间 (ISO 8601)")
    steps: List[WorkflowStep] = Field(..., description="按拓扑顺序排列的工作流步骤")


# ── API 请求/响应 ──

class IntentResponse(BaseModel):
    """意图理解响应"""
    success: bool = Field(..., description="是否成功")
    understood: str = Field(default="", description="AI 对用户意图的理解摘要")
    workflow: Optional[dict] = Field(default=None, description="结构化工作流 JSON")
    error: Optional[str] = Field(default=None, description="错误信息")
    validation_errors: List[str] = Field(default_factory=list, description="Schema 验证错误列表")
    raw_output: Optional[str] = Field(default=None, description="AI 原始输出（调试用）")
    retry_count: int = Field(default=0, description="重试次数")


class AssetRef(BaseModel):
    """素材库中的素材引用"""
    id: str = Field(..., description="素材唯一标识，如 asset_001")
    name: str = Field(..., description="素材名称，如'钢铁侠战甲'")
    type: str = Field(default="character", description="素材类型: character/background/object/effect")
    path: str = Field(..., description="素材文件路径")


class IntentRequest(BaseModel):
    """意图理解请求"""
    input: str = Field(
        ...,
        description="用户自然语言输入",
        min_length=1,
        max_length=2000,
    )
    assets: Optional[List[AssetRef]] = Field(
        default=None,
        description="当前项目的素材列表（用户已上传）。AI 只负责引用，不负责管理。",
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="可选的上下文信息（项目名、分辨率等）",
    )
    project_id: Optional[str] = Field(default=None, description="项目 ID")


# ── 状态回传 ──

class StepStatus(BaseModel):
    """步骤执行状态（本地 → 云端回传）"""
    step_index: int = Field(..., description="步骤索引")
    action: str = Field(..., description="工具名称")
    status: str = Field(..., description="pending/running/completed/failed")
    progress: float = Field(default=0.0, description="进度 0.0-1.0")
    output_path: Optional[str] = Field(default=None, description="输出文件路径")
    error: Optional[str] = Field(default=None, description="错误信息")
    duration_ms: Optional[int] = Field(default=None, description="执行耗时（毫秒）")


class WorkflowStatus(BaseModel):
    """工作流整体状态"""
    workflow_id: str = Field(..., description="工作流 ID")
    status: str = Field(..., description="pending/running/completed/failed")
    steps: List[StepStatus] = Field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None