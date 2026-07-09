"""
Memento-X 工作流任务数据模型

云端下发工作流任务的生命周期管理。
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


class TaskPriority(int, Enum):
    """任务优先级（数值越小优先级越高）"""
    HIGH = 0
    NORMAL = 1
    LOW = 2


class TaskStatus(str, Enum):
    """任务状态"""
    CREATED = "created"          # 已创建，等待下发
    QUEUED = "queued"            # 已入队，等待调度
    DISPATCHED = "dispatched"    # 已下发到本地
    ACCEPTED = "accepted"        # 本地已接收
    RUNNING = "running"          # 正在执行
    COMPLETED = "completed"      # 执行完成
    FAILED = "failed"            # 执行失败
    RETRYING = "retrying"        # 重试中
    PARTIAL = "partial"          # 部分成功
    CANCELLED = "cancelled"      # 已取消
    TIMEOUT = "timeout"          # 超时
    NEEDS_ASSET = "needs_asset"  # 需要用户上传素材


class DispatchRequest(BaseModel):
    """下发请求"""
    user_input: str = Field(..., description="用户自然语言输入")
    project_id: Optional[str] = Field(None, description="项目 ID")
    assets: Optional[List[dict]] = Field(None, description="素材库引用列表")
    context: Optional[str] = Field(None, description="额外上下文")
    local_url: Optional[str] = Field(None, description="用户本机 API 地址")
    priority: TaskPriority = Field(TaskPriority.NORMAL, description="任务优先级")


class DispatchResponse(BaseModel):
    """下发响应"""
    task_id: str = Field(..., description="任务 ID")
    status: str = Field("queued", description="下发状态")
    local_url: Optional[str] = Field(None, description="本地服务地址")
    message: str = Field("", description="状态消息")
    workflow_preview: Optional[dict] = Field(None, description="工作流预览（步骤摘要）")
    queue_position: Optional[int] = Field(None, description="队列位置（0=正在执行）")


class WorkflowTask(BaseModel):
    """工作流任务"""
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    user_id: str = Field("anonymous")
    project_id: Optional[str] = None
    user_input: str = ""
    status: TaskStatus = TaskStatus.CREATED
    priority: TaskPriority = TaskPriority.NORMAL
    workflow: Optional[dict] = None
    assets: Optional[List[dict]] = None
    local_url: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    current_step: Optional[str] = None
    step_status: Optional[str] = None
    progress: float = 0.0
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=datetime.utcnow)
    dispatched_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    class Config:
        use_enum_values = True


class LocalRegistration(BaseModel):
    """本地服务注册"""
    user_id: str = Field(..., description="用户 ID")
    host: str = Field(..., description="本地服务 IP")
    port: int = Field(8000, description="本地服务端口")
    version: str = Field("1.0.0", description="引擎版本")
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field("online", description="在线状态: online/offline/timeout")


class StatusReport(BaseModel):
    """状态上报"""
    task_id: str
    status: str
    step_id: Optional[str] = None
    step_status: Optional[str] = None
    progress: Optional[float] = None
    error: Optional[str] = None
    result: Optional[dict] = None


class HeartbeatRequest(BaseModel):
    """心跳请求"""
    user_id: str = Field(..., description="用户 ID")
    host: str = Field(..., description="本地服务 IP")
    port: int = Field(8000, description="本地服务端口")
    version: str = Field("1.0.0", description="引擎版本")
    active_tasks: int = Field(0, description="当前活跃任务数")
    gpu_available: bool = Field(True, description="GPU 是否可用")