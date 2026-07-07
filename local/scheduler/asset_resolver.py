"""
Memento-X 资产解析器

职责：
1. 根据 asset_id 查找本地素材路径
2. 管理素材库索引（asset_id → 本地文件路径）
3. 素材库扫描（从目录加载所有素材）
4. 素材查询（按名称、类型搜索）

边界：
- 只负责解析路径，不负责下载或管理素材
- AI 通过 asset_id 引用，Resolver 负责映射到本地路径
"""
import json
import os
import logging
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class AssetNotFoundError(Exception):
    """素材未找到"""
    def __init__(self, asset_id: str = "", asset_name: str = ""):
        self.asset_id = asset_id
        self.asset_name = asset_name
        msg = f"素材未找到: {asset_id or asset_name}"
        super().__init__(msg)


class AssetResolver:
    """
    资产解析器。

    维护 asset_id → 本地文件路径的映射表，支持：
    - 从 JSON 索引文件加载
    - 从目录扫描加载
    - 按名称/类型查询
    """

    def __init__(self, assets_dir: Optional[str] = None):
        """
        初始化。

        Args:
            assets_dir: 素材库根目录，默认 ~/.memento/assets/
        """
        self.assets_dir = Path(assets_dir or os.path.expanduser("~/.memento/assets"))
        self._index: Dict[str, dict] = {}  # asset_id → {"name", "type", "path"}
        self._name_index: Dict[str, str] = {}  # name → asset_id
        self._type_index: Dict[str, List[str]] = {}  # type → [asset_id, ...]

        # 自动加载索引
        if self.assets_dir.exists():
            self._load_index()

    # ── 公共 API ──

    def resolve(self, asset_id: str) -> str:
        """
        根据 asset_id 解析本地文件路径。

        Args:
            asset_id: 素材唯一标识，如 "asset_001"

        Returns:
            str: 本地文件绝对路径

        Raises:
            AssetNotFoundError: 如果 asset_id 不存在
        """
        if asset_id not in self._index:
            raise AssetNotFoundError(asset_id=asset_id)
        return self._index[asset_id]["path"]

    def resolve_or_none(self, asset_id: Optional[str]) -> Optional[str]:
        """
        安全解析：失败时返回 None 而不是抛异常。

        Args:
            asset_id: 素材 ID，null 或空字符串返回 None

        Returns:
            str | None: 本地路径或 None
        """
        if not asset_id:
            return None
        try:
            return self.resolve(asset_id)
        except AssetNotFoundError:
            return None

    def find_by_name(self, name: str) -> Optional[str]:
        """
        按名称查找素材的 asset_id。

        Args:
            name: 素材名称，如 "钢铁侠战甲"

        Returns:
            str | None: asset_id 或 None
        """
        return self._name_index.get(name)

    def find_by_type(self, asset_type: str) -> List[str]:
        """
        按类型查找所有素材的 asset_id。

        Args:
            asset_type: 素材类型，如 "character", "background"

        Returns:
            List[str]: asset_id 列表
        """
        return self._type_index.get(asset_type, [])

    def get_info(self, asset_id: str) -> Optional[dict]:
        """
        获取素材完整信息。

        Returns:
            dict: {"id", "name", "type", "path"} 或 None
        """
        if asset_id not in self._index:
            return None
        info = dict(self._index[asset_id])
        info["id"] = asset_id
        return info

    def list_all(self) -> List[dict]:
        """
        列出所有素材。

        Returns:
            List[dict]: 素材信息列表
        """
        return [
            {"id": aid, **info}
            for aid, info in self._index.items()
        ]

    def reload(self):
        """重新加载素材索引"""
        self._index.clear()
        self._name_index.clear()
        self._type_index.clear()
        self._load_index()

    # ── 内部方法 ──

    def _load_index(self):
        """从素材库目录加载索引"""
        index_file = self.assets_dir / "index.json"

        if index_file.exists():
            self._load_from_json(index_file)
        else:
            self._scan_directory()

        logger.info(f"素材库加载完成: {len(self._index)} 个素材")

    def _load_from_json(self, index_file: Path):
        """从 JSON 索引文件加载"""
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                assets = json.load(f)

            for asset in assets:
                aid = asset.get("id", "")
                if not aid:
                    continue

                self._index[aid] = {
                    "name": asset.get("name", aid),
                    "type": asset.get("type", "unknown"),
                    "path": asset.get("path", ""),
                }

                # 建立辅助索引
                name = asset.get("name", "")
                if name:
                    self._name_index[name] = aid

                atype = asset.get("type", "unknown")
                if atype not in self._type_index:
                    self._type_index[atype] = []
                self._type_index[atype].append(aid)

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"索引文件加载失败: {e}，回退到目录扫描")
            self._scan_directory()

    def _scan_directory(self):
        """扫描素材库目录，自动建立索引"""
        if not self.assets_dir.exists():
            logger.info(f"素材库目录不存在: {self.assets_dir}")
            return

        # 支持的图片/视频格式
        extensions = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".avi", ".webm"}

        for filepath in self.assets_dir.iterdir():
            if filepath.is_dir():
                continue
            if filepath.suffix.lower() not in extensions:
                continue

            # 从文件名生成 ID 和名称
            stem = filepath.stem
            aid = f"asset_{stem.replace(' ', '_').lower()}"
            name = stem.replace("_", " ").replace("-", " ")

            # 简易类型推断
            atype = "unknown"
            name_lower = name.lower()
            if any(kw in name_lower for kw in ["背景", "background", "bg", "场景"]):
                atype = "background"
            elif any(kw in name_lower for kw in ["人物", "角色", "character", "person"]):
                atype = "character"
            elif any(kw in name_lower for kw in ["物品", "物体", "object", "道具"]):
                atype = "object"
            elif any(kw in name_lower for kw in ["特效", "effect", "粒子", "火焰"]):
                atype = "effect"

            self._index[aid] = {
                "name": name,
                "type": atype,
                "path": str(filepath.absolute()),
            }

            self._name_index[name] = aid
            if atype not in self._type_index:
                self._type_index[atype] = []
            self._type_index[atype].append(aid)


# 全局解析器
asset_resolver = AssetResolver()