"""
Memento-X 工作流 Schema

定义从云端 AI 意图理解到本地调度器执行的标准化 JSON 指令格式。
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    """工作流中的单个步骤"""
    action: str = Field(..., description="工具名称: matting/tracking/replace/composite/color_grade/subtitle/effect/crop/stabilize/denoise")
    target: str = Field(default="", description="操作目标: person/background/object/foreground/mask")
    params: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    reason: str = Field(default="", description="为什么需要这一步")


class Workflow(BaseModel):
    """完整工作流"""
    steps: List[WorkflowStep] = Field(..., description="按顺序执行的工作流步骤")
    estimated_duration_seconds: int = Field(default=0, description="预估总耗时（秒）")


class IntentResponse(BaseModel):
    """意图理解响应"""
    success: bool = Field(..., description="是否成功")
    understood: str = Field(default="", description="AI 对用户意图的理解摘要")
    workflow: Optional[Workflow] = Field(default=None, description="结构化工作流")
    error: Optional[str] = Field(default=None, description="错误信息")
    raw_output: Optional[str] = Field(default=None, description="AI 原始输出（调试用）")


class IntentRequest(BaseModel):
    """意图理解请求"""
    input: str = Field(..., description="用户自然语言输入", min_length=1, max_length=2000)
    context: Optional[str] = Field(default=None, description="可选的上下文信息")
    project_id: Optional[str] = Field(default=None, description="项目 ID")


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