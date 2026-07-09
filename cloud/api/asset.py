"""
Memento-X 云端素材元数据 API

端点：
- POST /api/v1/asset/metadata   上传素材元数据 → 返回 asset_id
- POST /api/v1/asset/upload-url 获取预签名上传 URL（缩略图）
- GET  /api/v1/asset/list        获取素材列表
- GET  /api/v1/asset/{asset_id}  获取素材详情
"""
import uuid
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cloud.services.oss import (
    generate_presigned_upload_url,
    generate_thumbnail_key,
    get_thumbnail_url,
    get_object_url,
    object_exists,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 内存存储（生产环境接入 PostgreSQL）──
_assets: dict[str, dict] = {}


# ── 请求/响应模型 ──

class AssetMetadataRequest(BaseModel):
    """素材元数据上传请求"""
    name: str = Field(..., description="文件名")
    type: str = Field(..., description="类型: image/video")
    size_bytes: int = Field(..., description="文件大小（字节）")
    duration: Optional[float] = Field(None, description="视频时长（秒）")
    local_path: str = Field(..., description="本地文件路径")


class AssetMetadataResponse(BaseModel):
    """素材元数据上传响应"""
    asset_id: str = Field(..., description="云端分配的素材唯一标识")
    thumbnail_url: Optional[str] = Field(None, description="缩略图 URL")


class UploadUrlRequest(BaseModel):
    """预签名上传 URL 请求"""
    asset_id: str = Field(..., description="素材 ID")
    content_type: str = Field(default="image/jpeg", description="文件 MIME 类型")
    file_extension: str = Field(default="jpg", description="文件扩展名")


class UploadUrlResponse(BaseModel):
    """预签名上传 URL 响应"""
    upload_url: str = Field(..., description="预签名 PUT URL，客户端直接上传到 OSS")
    thumbnail_url: str = Field(..., description="上传完成后可访问的缩略图 URL")
    object_key: str = Field(..., description="OSS 对象存储路径")
    expires_in: int = Field(..., description="URL 有效期（秒）")


class AssetItem(BaseModel):
    """素材列表项"""
    asset_id: str
    name: str
    type: str
    duration: Optional[float] = None
    thumbnail_url: Optional[str] = None
    status: str = "ready"
    is_result: bool = False
    uploaded_at: int


# ── 端点 ──

@router.post("/metadata", response_model=AssetMetadataResponse)
async def upload_metadata(req: AssetMetadataRequest):
    """
    上传素材元数据。

    手机端调用此端点，仅上传元数据（文件名、类型、时长、缩略图），
    素材文件保留在手机本地。云端返回 asset_id。

    架构约束：云端不存储任何视频文件。
    """
    asset_id = f"asset_{uuid.uuid4().hex[:12]}"

    _assets[asset_id] = {
        "asset_id": asset_id,
        "name": req.name,
        "type": req.type,
        "size_bytes": req.size_bytes,
        "duration": req.duration,
        "local_path": req.local_path,
        "status": "ready",
        "is_result": False,
        "thumbnail_url": None,
        "uploaded_at": int(datetime.utcnow().timestamp()),
    }

    logger.info(f"素材元数据已注册: {asset_id} ({req.name})")
    return AssetMetadataResponse(asset_id=asset_id)


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_upload_url(req: UploadUrlRequest):
    """
    获取预签名上传 URL。

    客户端获取此 URL 后，直接 PUT 缩略图到阿里云 OSS，
    无需经过云端服务器中转。上传完成后调用此端点再次确认。

    架构约束：仅用于缩略图上传，不用于视频文件。
    """
    # 验证 asset_id 存在
    if req.asset_id not in _assets:
        raise HTTPException(status_code=404, detail="素材不存在")

    object_key = generate_thumbnail_key(req.asset_id, req.file_extension)
    upload_url = generate_presigned_upload_url(
        object_key=object_key,
        content_type=req.content_type,
    )
    thumbnail_url = get_thumbnail_url(object_key)

    # 更新素材记录
    _assets[req.asset_id]["thumbnail_url"] = thumbnail_url
    _assets[req.asset_id]["thumbnail_key"] = object_key

    logger.info(f"预签名上传 URL 已生成: {req.asset_id} → {object_key}")
    return UploadUrlResponse(
        upload_url=upload_url,
        thumbnail_url=thumbnail_url,
        object_key=object_key,
        expires_in=3600,
    )


@router.get("/list")
async def list_assets():
    """获取素材列表"""
    items = [
        AssetItem(
            asset_id=a["asset_id"],
            name=a["name"],
            type=a["type"],
            duration=a.get("duration"),
            thumbnail_url=a.get("thumbnail_url"),
            status=a.get("status", "ready"),
            is_result=a.get("is_result", False),
            uploaded_at=a.get("uploaded_at", 0),
        )
        for a in _assets.values()
    ]
    return items


@router.get("/{asset_id}")
async def get_asset(asset_id: str):
    """获取素材详情"""
    asset = _assets.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在")
    return AssetItem(
        asset_id=asset["asset_id"],
        name=asset["name"],
        type=asset["type"],
        duration=asset.get("duration"),
        thumbnail_url=asset.get("thumbnail_url"),
        status=asset.get("status", "ready"),
        is_result=asset.get("is_result", False),
        uploaded_at=asset.get("uploaded_at", 0),
    )