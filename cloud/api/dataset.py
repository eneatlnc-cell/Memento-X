"""
Memento-X 数据集控制层 API

全流程 JSON 标注数据集的管理端点：
- POST /api/v1/dataset/run/start     创建运行记录
- POST /api/v1/dataset/node/complete 节点完成回调
- GET  /api/v1/dataset/run/{run_id}  获取运行详情（含所有节点标注）
- GET  /api/v1/dataset/run/list      获取用户运行列表
- POST /api/v1/dataset/run/{run_id}/cancel  取消运行

数据持久化到 PostgreSQL dataset_runs + node_annotations 表。
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cloud.db.engine import async_session_factory
from cloud.db.crud import (
    dataset_run_create,
    dataset_run_get_by_id,
    dataset_run_get_by_user,
    dataset_run_start,
    dataset_run_complete,
    dataset_run_fail,
    dataset_run_update_node,
    node_annotation_upsert,
    node_annotation_get_by_run,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 节点名称映射 ──
NODE_NAMES = {
    1: "preprocess",
    2: "segment",
    3: "pose2d",
    4: "pose3d",
    5: "quadmask",
    6: "ltx",
}


# ── 请求/响应模型 ──

class RunStartRequest(BaseModel):
    """启动数据集运行请求"""
    user_id: str = Field(..., description="用户 ID")
    video_path: str = Field(..., description="视频文件路径")
    video_name: str = Field(..., description="视频文件名")
    task_id: Optional[str] = Field(None, description="关联的任务 ID")
    metadata: Optional[dict] = Field(None, description="额外元数据（分辨率、帧率等）")


class RunStartResponse(BaseModel):
    """启动数据集运行响应"""
    run_id: str
    status: str = "pending"
    message: str = "运行已创建，等待启动"


class NodeCompleteRequest(BaseModel):
    """节点完成回调请求"""
    run_id: str = Field(..., description="运行 ID")
    node_id: int = Field(..., ge=1, le=6, description="节点编号 (1-6)")
    status: str = Field(..., description="节点状态: completed / failed")
    output_path: Optional[str] = Field(None, description="节点输出路径")
    annotation_data: Optional[dict] = Field(None, description="节点标注数据（JSON）")
    error: Optional[str] = Field(None, description="错误信息（status=failed 时必填）")


class NodeCompleteResponse(BaseModel):
    """节点完成回调响应"""
    run_id: str
    node_id: int
    node_name: str
    status: str
    is_last_node: bool = False
    message: str


class NodeAnnotationItem(BaseModel):
    """节点标注项"""
    node_id: int
    node_name: str
    status: str
    output_path: Optional[str] = None
    annotation_data: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class RunDetailResponse(BaseModel):
    """运行详情响应"""
    run_id: str
    user_id: str
    video_path: str
    video_name: str
    status: str
    current_node: int
    total_nodes: int
    error: Optional[str] = None
    metadata: Optional[dict] = None
    annotations_path: Optional[str] = None
    node_annotations: List[NodeAnnotationItem] = []
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    created_at: float


class RunListItem(BaseModel):
    """运行列表项"""
    run_id: str
    video_name: str
    status: str
    current_node: int
    total_nodes: int
    created_at: float


# ── 端点 ──

@router.post("/run/start", response_model=RunStartResponse)
async def start_run(req: RunStartRequest):
    """
    创建数据集运行记录。

    调用时机：启动器开始处理一个视频时。
    云端创建 dataset_run + 6 条 node_annotation（全部 pending）。
    """
    async with async_session_factory() as db:
        run = await dataset_run_create(
            db,
            user_id=req.user_id,
            video_path=req.video_path,
            video_name=req.video_name,
            task_id=req.task_id,
            metadata_json=req.metadata,
        )

        # 预创建 6 个节点标注记录
        for node_id in range(1, 7):
            await node_annotation_upsert(
                db,
                run_id=run.run_id,
                node_id=node_id,
                node_name=NODE_NAMES[node_id],
                status="pending",
            )

    logger.info(f"数据集运行已创建: {run.run_id} ({req.video_name})")
    return RunStartResponse(run_id=run.run_id)


@router.post("/node/complete", response_model=NodeCompleteResponse)
async def complete_node(req: NodeCompleteRequest):
    """
    节点完成回调。

    调用时机：每个 pipeline 节点执行完毕后，启动器上报结果。
    云端更新 node_annotation 状态，并推进 dataset_run.current_node。

    节点 6 完成时自动标记整个 run 为 completed。
    """
    async with async_session_factory() as db:
        run = await dataset_run_get_by_id(db, req.run_id)
        if not run:
            raise HTTPException(status_code=404, detail="运行记录不存在")

        # 验证节点编号
        if req.node_id < 1 or req.node_id > 6:
            raise HTTPException(status_code=400, detail="节点编号必须在 1-6 之间")

        node_name = NODE_NAMES[req.node_id]

        # 更新节点标注
        await node_annotation_upsert(
            db,
            run_id=req.run_id,
            node_id=req.node_id,
            node_name=node_name,
            status=req.status,
            output_path=req.output_path,
            annotation_data=req.annotation_data,
            error=req.error,
        )

        is_last_node = req.node_id == 6

        if req.status == "failed":
            # 节点失败 → 整个 run 失败
            await dataset_run_fail(db, req.run_id, req.error or f"节点 {node_name} 执行失败")
            logger.warning(f"数据集运行失败: {req.run_id} @ node {req.node_id} ({node_name})")
            return NodeCompleteResponse(
                run_id=req.run_id,
                node_id=req.node_id,
                node_name=node_name,
                status="failed",
                is_last_node=False,
                message=f"节点 {node_name} 失败，运行已终止",
            )

        if is_last_node:
            # 最后一个节点完成
            await dataset_run_complete(db, req.run_id, req.output_path)
            logger.info(f"数据集运行完成: {req.run_id} (全部 6 个节点)")
            return NodeCompleteResponse(
                run_id=req.run_id,
                node_id=req.node_id,
                node_name=node_name,
                status="completed",
                is_last_node=True,
                message="全部 6 个节点已完成，运行结束",
            )

        # 推进到下一个节点
        next_node = req.node_id + 1
        await dataset_run_update_node(db, req.run_id, next_node)

        # 标记下一个节点为 running
        await node_annotation_upsert(
            db,
            run_id=req.run_id,
            node_id=next_node,
            node_name=NODE_NAMES[next_node],
            status="running",
        )

        logger.info(f"节点完成: {req.run_id} node {req.node_id} ({node_name}) → 推进到 node {next_node}")

    return NodeCompleteResponse(
        run_id=req.run_id,
        node_id=req.node_id,
        node_name=node_name,
        status="completed",
        is_last_node=False,
        message=f"节点 {node_name} 完成，推进到 {NODE_NAMES[next_node]}",
    )


@router.get("/run/{run_id}", response_model=RunDetailResponse)
async def get_run_detail(run_id: str):
    """
    获取运行详情（含所有节点标注数据）。

    返回完整的 dataset_run + 6 条 node_annotation。
    """
    async with async_session_factory() as db:
        run = await dataset_run_get_by_id(db, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="运行记录不存在")

        annotations = await node_annotation_get_by_run(db, run_id)

    return RunDetailResponse(
        run_id=run.run_id,
        user_id=run.user_id,
        video_path=run.video_path,
        video_name=run.video_name,
        status=run.status,
        current_node=run.current_node,
        total_nodes=run.total_nodes,
        error=run.error,
        metadata=run.metadata_json,
        annotations_path=run.annotations_path,
        node_annotations=[
            NodeAnnotationItem(
                node_id=a.node_id,
                node_name=a.node_name,
                status=a.status,
                output_path=a.output_path,
                annotation_data=a.annotation_data,
                error=a.error,
                started_at=a.started_at.timestamp() if a.started_at else None,
                completed_at=a.completed_at.timestamp() if a.completed_at else None,
            )
            for a in annotations
        ],
        started_at=run.started_at.timestamp() if run.started_at else None,
        completed_at=run.completed_at.timestamp() if run.completed_at else None,
        created_at=run.created_at.timestamp(),
    )


@router.get("/run/list")
async def list_runs(user_id: str, limit: int = 50):
    """
    获取用户的运行列表。

    Query params:
        user_id: 用户 ID
        limit: 返回数量上限（默认 50）
    """
    async with async_session_factory() as db:
        runs = await dataset_run_get_by_user(db, user_id, limit)

    return [
        RunListItem(
            run_id=r.run_id,
            video_name=r.video_name,
            status=r.status,
            current_node=r.current_node,
            total_nodes=r.total_nodes,
            created_at=r.created_at.timestamp(),
        )
        for r in runs
    ]


@router.post("/run/{run_id}/cancel")
async def cancel_run(run_id: str):
    """
    取消运行。

    将运行状态标记为 failed，错误信息为 "用户取消"。
    """
    async with async_session_factory() as db:
        run = await dataset_run_get_by_id(db, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="运行记录不存在")

        if run.status not in ("pending", "running"):
            raise HTTPException(status_code=400, detail="运行状态不允许取消")

        await dataset_run_fail(db, run_id, "用户取消")

    logger.info(f"数据集运行已取消: {run_id}")
    return {"run_id": run_id, "status": "cancelled", "message": "运行已取消"}