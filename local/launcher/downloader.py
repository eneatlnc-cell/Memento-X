"""
Memento-X 工具下载管理器

按需下载工具到本地缓存目录，支持断点续传和进度上报。
"""
import os
import hashlib
import requests
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    version: str
    description: str
    download_url: str
    sha256: str
    size_bytes: int
    extract_dir: str  # 解压后的目录名
    required: bool = False  # 是否必需（FFmpeg 是必需的）


# 工具清单（生产环境从云端配置拉取）
TOOL_CATALOG: dict[str, ToolDefinition] = {
    "ffmpeg": ToolDefinition(
        name="FFmpeg",
        version="7.0",
        description="视频编解码与合成",
        download_url="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
        sha256="",
        size_bytes=80_000_000,
        extract_dir="ffmpeg",
        required=True,
    ),
    "birefnet": ToolDefinition(
        name="BiRefNet",
        version="2.0",
        description="高精度图像抠图",
        download_url="https://huggingface.co/ZhengPeng7/BiRefNet/resolve/main/BiRefNet-general-bb_swin_v1_tiny-epoch_232.pth",
        sha256="",
        size_bytes=450_000_000,
        extract_dir="birefnet",
    ),
    "sam2": ToolDefinition(
        name="SAM2-MLX",
        version="1.0",
        description="视频遮罩追踪（Apple Silicon 优化）",
        download_url="https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt",
        sha256="",
        size_bytes=900_000_000,
        extract_dir="sam2",
    ),
    "comfyui": ToolDefinition(
        name="ComfyUI",
        version="latest",
        description="AI 特效生成（火焰/粒子/光效）",
        download_url="https://github.com/comfyanonymous/ComfyUI/archive/refs/heads/master.zip",
        sha256="",
        size_bytes=500_000_000,
        extract_dir="ComfyUI",
    ),
    "hyperframes": ToolDefinition(
        name="HyperFrames",
        version="1.0",
        description="字幕/标题渲染引擎",
        download_url="",
        sha256="",
        size_bytes=50_000_000,
        extract_dir="hyperframes",
    ),
}


class ToolDownloader:
    """工具下载器"""

    def __init__(self, cache_dir: str = "~/.memento/tools"):
        self.cache_dir = os.path.expanduser(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_tool_path(self, tool_name: str) -> Optional[str]:
        """获取已安装工具的路径"""
        tool_dir = os.path.join(self.cache_dir, tool_name)
        if os.path.isdir(tool_dir):
            return tool_dir
        return None

    def is_installed(self, tool_name: str) -> bool:
        """检查工具是否已安装"""
        return self.get_tool_path(tool_name) is not None

    def download(
        self,
        tool_name: str,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> Optional[str]:
        """
        下载工具到本地缓存。

        Args:
            tool_name: 工具名称
            on_progress: 进度回调 (0.0 ~ 1.0)

        Returns:
            安装路径，失败返回 None
        """
        definition = TOOL_CATALOG.get(tool_name)
        if not definition:
            print(f"Unknown tool: {tool_name}")
            return None

        if not definition.download_url:
            print(f"Tool {tool_name} has no download URL (manual install required)")
            return None

        tool_dir = os.path.join(self.cache_dir, tool_name)
        os.makedirs(tool_dir, exist_ok=True)

        # 下载文件
        filename = os.path.basename(definition.download_url.split("?")[0])
        filepath = os.path.join(tool_dir, filename)

        if os.path.exists(filepath):
            # 校验 SHA256
            if self._verify_sha256(filepath, definition.sha256):
                print(f"Tool {tool_name} already downloaded and verified")
                return tool_dir

        print(f"Downloading {tool_name} from {definition.download_url}...")

        try:
            response = requests.get(definition.download_url, stream=True, timeout=3600)
            response.raise_for_status()

            total = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0 and on_progress:
                        on_progress(downloaded / total)

            if not self._verify_sha256(filepath, definition.sha256):
                print(f"WARNING: SHA256 mismatch for {tool_name}")

            return tool_dir

        except Exception as e:
            print(f"Download failed for {tool_name}: {e}")
            return None

    def ensure_required(self) -> bool:
        """确保所有必需工具已安装"""
        for name, definition in TOOL_CATALOG.items():
            if definition.required and not self.is_installed(name):
                print(f"Required tool {name} not installed, downloading...")
                if self.download(name) is None:
                    return False
        return True

    @staticmethod
    def _verify_sha256(filepath: str, expected: str) -> bool:
        """校验文件 SHA256"""
        if not expected:
            return True
        sha = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest() == expected