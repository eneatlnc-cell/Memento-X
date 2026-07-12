"""
Memento-X 数据库 CRUD 操作

每个模块提供独立的异步 CRUD 函数，供 API 层和 Service 层调用。
所有函数均接受 AsyncSession 作为第一个参数。
"""
import logging
from datetime import date, datetime, timezone
from typing import Optional, List

from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.db.models import (
    User, Launcher, Task, Quota,
    DatasetRun, NodeAnnotation,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# User CRUD
# ════════════════════════════════════════════════════════════════════

async def user_create(db: AsyncSession, email: str, password_hash: str, tier: str = "free") -> User | None:
    """创建用户；邮箱已存在返回 None"""
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        return None
    user = User(email=email, password_hash=password_hash, tier=tier)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def user_get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def user_get_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ════════════════════════════════════════════════════════════════════
# Launcher CRUD
# ════════════════════════════════════════════════════════════════════

async def launcher_upsert(
    db: AsyncSession,
    user_id: str,
    host: str,
    port: int,
    version: str = "1.0.0",
) -> Launcher:
    """注册或更新启动器信息（upsert）"""
    existing = await db.execute(
        select(Launcher).where(Launcher.user_id == user_id)
    )
    launcher = existing.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if launcher:
        launcher.host = host
        launcher.port = port
        launcher.version = version
        launcher.status = "online"
        launcher.last_heartbeat = now
    else:
        launcher = Launcher(
            user_id=user_id,
            host=host,
            port=port,
            version=version,
            status="online",
            last_heartbeat=now,
        )
        db.add(launcher)

    await db.commit()
    await db.refresh(launcher)
    return launcher


async def launcher_get_by_user(db: AsyncSession, user_id: str) -> Launcher | None:
    result = await db.execute(
        select(Launcher).where(Launcher.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def launcher_get_all(db: AsyncSession) -> List[Launcher]:
    result = await db.execute(select(Launcher))
    return list(result.scalars().all())


async def launcher_update_heartbeat(
    db: AsyncSession, user_id: str, host: str, port: int,
    version: str = "1.0.0",
) -> bool:
    """更新心跳时间；返回是否为新注册"""
    existing = await launcher_get_by_user(db, user_id)
    if existing:
        existing.host = host
        existing.port = port
        existing.version = version
        existing.status = "online"
        existing.last_heartbeat = datetime.now(timezone.utc)
        await db.commit()
        return False
    else:
        await launcher_upsert(db, user_id, host, port, version)
        return True


async def launcher_set_status(db: AsyncSession, user_id: str, status: str) -> None:
    """更新启动器状态"""
    await db.execute(
        update(Launcher)
        .where(Launcher.user_id == user_id)
        .values(status=status)
    )
    await db.commit()


async def launcher_get_timeout_candidates(
    db: AsyncSession, timeout_seconds: int = 90,
) -> List[Launcher]:
    """获取超时未心跳的启动器列表"""
    from datetime import timedelta
    threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    result = await db.execute(
        select(Launcher).where(
            and_(
                Launcher.status == "online",
                Launcher.last_heartbeat < threshold,
            )
        )
    )
    return list(result.scalars().all())


async def launcher_delete(db: AsyncSession, user_id: str) -> None:
    await db.execute(delete(Launcher).where(Launcher.user_id == user_id))
    await db.commit()


# ════════════════════════════════════════════════════════════════════
# Task CRUD
# ════════════════════════════════════════════════════════════════════

async def task_create(db: AsyncSession, **kwargs) -> Task:
    task = Task(**kwargs)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def task_get_by_id(db: AsyncSession, task_id: str) -> Task | None:
    result = await db.execute(
        select(Task).where(Task.task_id == task_id)
    )
    return result.scalar_one_or_none()


async def task_get_by_user(db: AsyncSession, user_id: str, limit: int = 50) -> List[Task]:
    result = await db.execute(
        select(Task)
        .where(Task.user_id == user_id)
        .order_by(Task.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def task_update_status(
    db: AsyncSession, task_id: str, status: str,
    **extra_fields,
) -> None:
    values = {"status": status, **extra_fields}
    await db.execute(
        update(Task).where(Task.task_id == task_id).values(**values)
    )
    await db.commit()


async def task_update_step(
    db: AsyncSession, task_id: str,
    current_step: str, step_status: str, progress: float,
) -> None:
    await db.execute(
        update(Task)
        .where(Task.task_id == task_id)
        .values(
            current_step=current_step,
            step_status=step_status,
            progress=progress,
        )
    )
    await db.commit()


async def task_complete(
    db: AsyncSession, task_id: str,
    result: dict | None = None,
) -> None:
    values = {
        "status": "completed",
        "result": result,
        "completed_at": datetime.now(timezone.utc),
        "progress": 1.0,
    }
    await db.execute(
        update(Task).where(Task.task_id == task_id).values(**values)
    )
    await db.commit()


async def task_fail(db: AsyncSession, task_id: str, error: str) -> None:
    await db.execute(
        update(Task)
        .where(Task.task_id == task_id)
        .values(
            status="failed",
            error=error,
            completed_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


# ════════════════════════════════════════════════════════════════════
# Quota CRUD
# ════════════════════════════════════════════════════════════════════

async def quota_get_today(db: AsyncSession, user_id: str) -> Quota:
    """获取今日配额记录，不存在则创建"""
    today = date.today()
    result = await db.execute(
        select(Quota).where(
            and_(Quota.user_id == user_id, Quota.date == today)
        )
    )
    quota = result.scalar_one_or_none()
    if not quota:
        quota = Quota(user_id=user_id, date=today, count=0)
        db.add(quota)
        await db.commit()
        await db.refresh(quota)
    return quota


async def quota_increment(db: AsyncSession, user_id: str) -> Quota:
    """今日配额 +1"""
    quota = await quota_get_today(db, user_id)
    quota.count += 1
    await db.commit()
    await db.refresh(quota)
    return quota


# ════════════════════════════════════════════════════════════════════
# DatasetRun CRUD
# ════════════════════════════════════════════════════════════════════

async def dataset_run_create(
    db: AsyncSession,
    user_id: str,
    video_path: str,
    video_name: str,
    task_id: str | None = None,
    metadata_json: dict | None = None,
) -> DatasetRun:
    run = DatasetRun(
        run_id=f"run_{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        task_id=task_id,
        video_path=video_path,
        video_name=video_name,
        metadata_json=metadata_json,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def dataset_run_get_by_id(db: AsyncSession, run_id: str) -> DatasetRun | None:
    result = await db.execute(
        select(DatasetRun).where(DatasetRun.run_id == run_id)
    )
    return result.scalar_one_or_none()


async def dataset_run_get_by_user(
    db: AsyncSession, user_id: str, limit: int = 50,
) -> List[DatasetRun]:
    result = await db.execute(
        select(DatasetRun)
        .where(DatasetRun.user_id == user_id)
        .order_by(DatasetRun.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def dataset_run_start(db: AsyncSession, run_id: str) -> None:
    await db.execute(
        update(DatasetRun)
        .where(DatasetRun.run_id == run_id)
        .values(
            status="running",
            started_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


async def dataset_run_complete(
    db: AsyncSession, run_id: str,
    annotations_path: str | None = None,
) -> None:
    await db.execute(
        update(DatasetRun)
        .where(DatasetRun.run_id == run_id)
        .values(
            status="completed",
            annotations_path=annotations_path,
            completed_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


async def dataset_run_fail(db: AsyncSession, run_id: str, error: str) -> None:
    await db.execute(
        update(DatasetRun)
        .where(DatasetRun.run_id == run_id)
        .values(
            status="failed",
            error=error,
            completed_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


async def dataset_run_update_node(
    db: AsyncSession, run_id: str, current_node: int,
) -> None:
    await db.execute(
        update(DatasetRun)
        .where(DatasetRun.run_id == run_id)
        .values(current_node=current_node)
    )
    await db.commit()


# ════════════════════════════════════════════════════════════════════
# NodeAnnotation CRUD
# ════════════════════════════════════════════════════════════════════

async def node_annotation_upsert(
    db: AsyncSession,
    run_id: str,
    node_id: int,
    node_name: str,
    status: str = "pending",
    output_path: str | None = None,
    annotation_data: dict | None = None,
    error: str | None = None,
) -> NodeAnnotation:
    """创建或更新节点标注记录"""
    existing = await db.execute(
        select(NodeAnnotation).where(
            and_(
                NodeAnnotation.run_id == run_id,
                NodeAnnotation.node_id == node_id,
            )
        )
    )
    annotation = existing.scalar_one_or_none()

    if annotation:
        annotation.status = status
        annotation.node_name = node_name
        if output_path is not None:
            annotation.output_path = output_path
        if annotation_data is not None:
            annotation.annotation_data = annotation_data
        if error is not None:
            annotation.error = error
        if status == "running" and annotation.started_at is None:
            annotation.started_at = datetime.now(timezone.utc)
        if status == "completed":
            annotation.completed_at = datetime.now(timezone.utc)
    else:
        annotation = NodeAnnotation(
            run_id=run_id,
            node_id=node_id,
            node_name=node_name,
            status=status,
            output_path=output_path,
            annotation_data=annotation_data,
            error=error,
            started_at=datetime.now(timezone.utc) if status == "running" else None,
            completed_at=datetime.now(timezone.utc) if status == "completed" else None,
        )
        db.add(annotation)

    await db.commit()
    await db.refresh(annotation)
    return annotation


async def node_annotation_get_by_run(
    db: AsyncSession, run_id: str,
) -> List[NodeAnnotation]:
    result = await db.execute(
        select(NodeAnnotation)
        .where(NodeAnnotation.run_id == run_id)
        .order_by(NodeAnnotation.node_id)
    )
    return list(result.scalars().all())


# 需要 uuid 模块
import uuid