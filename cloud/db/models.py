"""
Memento-X SQLAlchemy ORM 模型

所有持久化数据表定义：
- User: 用户账号
- Launcher: 本地引擎注册
- Task: 工作流任务
- Quota: 每日配额
- DatasetRun: 数据集运行记录
- NodeAnnotation: 节点标注数据
"""
import uuid
from datetime import datetime, date, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Date, DateTime, Text,
    ForeignKey, JSON, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from cloud.db.engine import Base


def _utcnow():
    return datetime.now(timezone.utc)


def _new_uuid():
    return uuid.uuid4().hex[:12]


# ────────────────────────────────────────────────────────────────────
# User — 用户账号
# ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id          = Column(String(32), primary_key=True, default=_new_uuid)
    email       = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    tier        = Column(String(20), default="free", nullable=False)  # free / pro / enterprise
    created_at  = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at  = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    launchers   = relationship("Launcher", back_populates="user", cascade="all, delete-orphan")
    tasks       = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    quotas      = relationship("Quota", back_populates="user", cascade="all, delete-orphan")
    dataset_runs = relationship("DatasetRun", back_populates="user", cascade="all, delete-orphan")


# ────────────────────────────────────────────────────────────────────
# Launcher — 本地引擎注册
# ────────────────────────────────────────────────────────────────────

class Launcher(Base):
    __tablename__ = "launchers"

    id             = Column(String(32), primary_key=True, default=_new_uuid)
    user_id        = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    host           = Column(String(255), nullable=False)
    port           = Column(Integer, default=8000, nullable=False)
    version        = Column(String(20), default="1.0.0", nullable=False)
    status         = Column(String(20), default="online", nullable=False)  # online / offline / timeout
    last_heartbeat = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    registered_at  = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at     = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user = relationship("User", back_populates="launchers")


# ────────────────────────────────────────────────────────────────────
# Task — 工作流任务
# ────────────────────────────────────────────────────────────────────

class Task(Base):
    __tablename__ = "tasks"

    id            = Column(String(32), primary_key=True, default=_new_uuid)
    task_id       = Column(String(64), unique=True, nullable=False, index=True)
    user_id       = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id    = Column(String(64), nullable=True)
    user_input    = Column(Text, default="", nullable=False)
    status        = Column(String(20), default="created", nullable=False)
    priority      = Column(Integer, default=1, nullable=False)
    workflow      = Column(JSON, nullable=True)
    assets        = Column(JSON, nullable=True)
    local_url     = Column(String(512), nullable=True)
    result        = Column(JSON, nullable=True)
    error         = Column(Text, nullable=True)
    current_step  = Column(String(64), nullable=True)
    step_status   = Column(String(20), nullable=True)
    progress      = Column(Float, default=0.0, nullable=False)
    retry_count   = Column(Integer, default=0, nullable=False)
    max_retries   = Column(Integer, default=3, nullable=False)
    created_at    = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    completed_at  = Column(DateTime(timezone=True), nullable=True)
    duration_ms   = Column(Integer, nullable=True)

    user = relationship("User", back_populates="tasks")
    dataset_runs = relationship("DatasetRun", back_populates="task")

    __table_args__ = (
        Index("ix_tasks_user_status", "user_id", "status"),
        Index("ix_tasks_created", "created_at"),
    )


# ────────────────────────────────────────────────────────────────────
# Quota — 每日配额
# ────────────────────────────────────────────────────────────────────

class Quota(Base):
    __tablename__ = "quotas"

    id      = Column(String(32), primary_key=True, default=_new_uuid)
    user_id = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date    = Column(Date, nullable=False)
    count   = Column(Integer, default=0, nullable=False)

    user = relationship("User", back_populates="quotas")

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_quota_user_date"),
        Index("ix_quota_user_date", "user_id", "date"),
    )


# ────────────────────────────────────────────────────────────────────
# DatasetRun — 数据集运行记录（全流程 JSON 标注控制）
# ────────────────────────────────────────────────────────────────────

class DatasetRun(Base):
    __tablename__ = "dataset_runs"

    id               = Column(String(32), primary_key=True, default=_new_uuid)
    run_id           = Column(String(64), unique=True, nullable=False, index=True)
    user_id          = Column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id          = Column(String(64), ForeignKey("tasks.task_id", ondelete="SET NULL"), nullable=True)
    video_path       = Column(String(1024), nullable=False)
    video_name       = Column(String(255), nullable=False)
    status           = Column(String(20), default="pending", nullable=False)  # pending/running/completed/failed
    current_node     = Column(Integer, default=0, nullable=False)
    total_nodes      = Column(Integer, default=6, nullable=False)
    error            = Column(Text, nullable=True)
    metadata_json    = Column(JSON, nullable=True)
    annotations_path = Column(String(1024), nullable=True)
    started_at       = Column(DateTime(timezone=True), nullable=True)
    completed_at     = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user = relationship("User", back_populates="dataset_runs")
    task = relationship("Task", back_populates="dataset_runs")
    node_annotations = relationship("NodeAnnotation", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_dataset_runs_user_status", "user_id", "status"),
    )


# ────────────────────────────────────────────────────────────────────
# NodeAnnotation — 节点标注数据
# ────────────────────────────────────────────────────────────────────

class NodeAnnotation(Base):
    __tablename__ = "node_annotations"

    id              = Column(String(32), primary_key=True, default=_new_uuid)
    run_id          = Column(String(64), ForeignKey("dataset_runs.run_id", ondelete="CASCADE"), nullable=False)
    node_id         = Column(Integer, nullable=False)  # 1-6
    node_name       = Column(String(64), nullable=False)
    status          = Column(String(20), default="pending", nullable=False)  # pending/running/completed/failed
    output_path     = Column(String(1024), nullable=True)
    annotation_data = Column(JSON, nullable=True)
    error           = Column(Text, nullable=True)
    started_at      = Column(DateTime(timezone=True), nullable=True)
    completed_at    = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    run = relationship("DatasetRun", back_populates="node_annotations")

    __table_args__ = (
        UniqueConstraint("run_id", "node_id", name="uq_node_annotation_run_node"),
        Index("ix_node_annotations_run", "run_id"),
    )


# ────────────────────────────────────────────────────────────────────
# all_models 列表 — 确保 init_db() 可导入所有模型
# ────────────────────────────────────────────────────────────────────

all_models = [User, Launcher, Task, Quota, DatasetRun, NodeAnnotation]