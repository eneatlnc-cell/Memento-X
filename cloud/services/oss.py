"""
Memento-X 阿里云 OSS 适配器（S3 兼容模式）

使用 boto3 S3 客户端通过阿里云 OSS 兼容端点访问对象存储。
提供预签名 URL 上传、缩略图生成、基础对象操作。

依赖：
    pip install boto3
"""
import logging
from typing import Optional
from urllib.parse import urljoin

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from cloud.config import settings

logger = logging.getLogger(__name__)

# ── boto3 S3 客户端（单例）──
_s3_client: Optional[object] = None


def _get_client():
    """获取或创建 boto3 S3 客户端（阿里云 OSS 兼容模式）"""
    global _s3_client
    if _s3_client is None:
        boto_config = BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
            region_name=settings.oss_region,
        )
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.oss_endpoint,
            aws_access_key_id=settings.oss_access_key_id,
            aws_secret_access_key=settings.oss_access_key_secret,
            config=boto_config,
        )
        logger.info(f"OSS 客户端已初始化: endpoint={settings.oss_endpoint}, bucket={settings.oss_bucket}")
    return _s3_client


# ── 公开 API ──


def generate_presigned_upload_url(
    object_key: str,
    content_type: str = "application/octet-stream",
    expire_seconds: Optional[int] = None,
) -> str:
    """
    生成预签名上传 URL。

    客户端使用此 URL 直接 PUT 文件到 OSS，无需经过云端服务器。

    Args:
        object_key: 对象存储路径（如 "thumbnails/asset_abc123.jpg"）
        content_type: 上传文件的 MIME 类型
        expire_seconds: URL 有效期（秒），默认 3600

    Returns:
        预签名 PUT URL
    """
    client = _get_client()
    expire = expire_seconds or settings.oss_presigned_url_expire

    url = client.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": settings.oss_bucket,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=expire,
        HttpMethod="PUT",
    )
    logger.debug(f"生成预签名上传 URL: {object_key} (expire={expire}s)")
    return url


def generate_presigned_download_url(
    object_key: str,
    expire_seconds: Optional[int] = None,
) -> str:
    """
    生成预签名下载 URL。

    Args:
        object_key: 对象存储路径
        expire_seconds: URL 有效期（秒）

    Returns:
        预签名 GET URL
    """
    client = _get_client()
    expire = expire_seconds or settings.oss_presigned_url_expire

    url = client.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": settings.oss_bucket,
            "Key": object_key,
        },
        ExpiresIn=expire,
    )
    return url


def get_thumbnail_url(object_key: str) -> str:
    """
    获取 OSS 缩略图处理 URL。

    使用阿里云 OSS 图片处理功能自动生成缩略图。
    格式: x-oss-process=image/resize,m_fill,w_400,h_225

    Args:
        object_key: 原始图片的对象路径

    Returns:
        带缩略图处理参数的完整 URL
    """
    base_url = f"https://{settings.oss_bucket}.{settings.oss_endpoint.replace('https://', '')}"
    thumbnail_params = "x-oss-process=image/resize,m_fill,w_400,h_225"
    return f"{base_url}/{object_key}?{thumbnail_params}"


def get_object_url(object_key: str) -> str:
    """获取对象的公开访问 URL"""
    base_url = f"https://{settings.oss_bucket}.{settings.oss_endpoint.replace('https://', '')}"
    return f"{base_url}/{object_key}"


def object_exists(object_key: str) -> bool:
    """检查对象是否存在"""
    client = _get_client()
    try:
        client.head_object(Bucket=settings.oss_bucket, Key=object_key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def delete_object(object_key: str) -> bool:
    """删除对象，返回是否成功"""
    client = _get_client()
    try:
        client.delete_object(Bucket=settings.oss_bucket, Key=object_key)
        logger.info(f"已删除 OSS 对象: {object_key}")
        return True
    except ClientError as e:
        logger.error(f"删除 OSS 对象失败: {object_key} — {e}")
        return False


def generate_thumbnail_key(asset_id: str, extension: str = "jpg") -> str:
    """
    生成缩略图的对象存储路径。

    Args:
        asset_id: 素材 ID
        extension: 文件扩展名

    Returns:
        对象存储路径，如 "thumbnails/asset_abc123.jpg"
    """
    return f"{settings.oss_thumbnail_prefix}{asset_id}.{extension}"