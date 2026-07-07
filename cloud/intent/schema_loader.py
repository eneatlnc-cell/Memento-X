"""
Memento-X Schema 加载器

职责：
1. 加载 schema/workflow.json
2. 提取工具信息（名称、参数、枚举值）用于 Prompt 构建
3. 验证 AI 输出是否符合 Schema
"""
import json
import logging
from pathlib import Path
from typing import Optional

import jsonschema

from cloud.config import settings

logger = logging.getLogger(__name__)


class SchemaLoader:
    """JSON Schema 加载与验证工具"""

    def __init__(self, schema_path: Optional[str] = None):
        """
        初始化 Schema 加载器。

        Args:
            schema_path: schema/workflow.json 的路径，默认从配置读取
        """
        self.schema_path = Path(schema_path or settings.schema_path)
        self._schema: Optional[dict] = None

    @property
    def schema(self) -> dict:
        """懒加载 Schema JSON"""
        if self._schema is None:
            self._schema = self._load_schema()
        return self._schema

    def _load_schema(self) -> dict:
        """从文件加载 JSON Schema"""
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema 文件不存在: {self.schema_path}")

        with open(self.schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        # 验证 Schema 本身合法性
        try:
            jsonschema.Draft7Validator.check_schema(schema)
        except jsonschema.SchemaError as e:
            raise ValueError(f"Schema 定义不合法: {e.message}")

        logger.info(f"Schema 加载成功: {self.schema_path} (v{schema.get('version', 'unknown')})")
        return schema

    def get_tool_names(self) -> list[str]:
        """获取所有可用工具名称列表"""
        step_def = self.schema.get("definitions", {}).get("Step", {})
        action_prop = step_def.get("properties", {}).get("action", {})
        return action_prop.get("enum", [])

    def get_tool_params(self, tool_name: str) -> dict:
        """
        获取指定工具的参数定义。

        Returns:
            dict: {
                "properties": {...},  # 参数名 → {type, description, default, enum, minimum, maximum}
            }
        """
        # 从 definitions 中查找对应的 Params 定义
        param_map = {
            "matting": "MattingParams",
            "track": "TrackParams",
            "replace": "ReplaceParams",
            "composite": "CompositeParams",
            "effect": "EffectParams",
            "color": "ColorParams",
            "subtitle": "SubtitleParams",
            "render": "RenderParams",
            "crop": "CropParams",
            "export": "ExportParams",
        }

        def_name = param_map.get(tool_name)
        if not def_name:
            return {"properties": {}}

        return self.schema.get("definitions", {}).get(def_name, {"properties": {}})

    def get_step_schema(self) -> dict:
        """获取 Step 的通用 Schema（id, action, target, depends_on 等）"""
        return self.schema.get("definitions", {}).get("Step", {})

    def get_target_values(self) -> list[str]:
        """获取 target 字段的枚举值"""
        step_def = self.get_step_schema()
        target_prop = step_def.get("properties", {}).get("target", {})
        return target_prop.get("enum", [])

    def validate(self, workflow: dict) -> list[str]:
        """
        验证工作流 JSON 是否符合 Schema。

        Returns:
            list[str]: 错误信息列表，空列表表示验证通过
        """
        errors = []
        try:
            jsonschema.validate(workflow, self.schema)
        except jsonschema.ValidationError as e:
            # 收集所有验证错误
            validator = jsonschema.Draft7Validator(self.schema)
            for err in validator.iter_errors(workflow):
                path = " → ".join(str(p) for p in err.path) if err.path else "根"
                errors.append(f"[{path}] {err.message}")
        return errors

    def reload(self):
        """强制重新加载 Schema（开发时热更新用）"""
        self._schema = None
        self._load_schema()
        logger.info("Schema 已重新加载")


# 全局 Schema 加载器
schema_loader = SchemaLoader()