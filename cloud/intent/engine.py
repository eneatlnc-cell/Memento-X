"""
Memento-X 意图理解引擎

核心链路：
用户输入 + assets → engine.process() → 调用通义千问VL-Pro → 解析JSON → 验证Schema → 返回工作流JSON

这是 Memento-X 唯一需要 AI 参与的环节。
AI 只做意图理解 + 素材引用，后续所有像素级工作由本地确定性工具完成。

素材库边界：
- AI 能做的：读取 assets 列表 → 匹配用户指令 → 在输出中使用 asset_id
- AI 不能做的：添加素材、删除素材、修改素材路径、捏造不存在的 asset_id
"""
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from dashscope import Generation

from cloud.config import settings
from cloud.intent.schema_loader import schema_loader
from cloud.intent.prompts import (
    build_system_prompt,
    build_user_prompt,
    build_correction_prompt,
)

logger = logging.getLogger(__name__)


# ── 自定义异常 ──

class IntentError(Exception):
    """意图理解失败"""
    def __init__(self, message: str, raw_output: str = ""):
        super().__init__(message)
        self.raw_output = raw_output


class SchemaValidationError(IntentError):
    """AI 输出不符合 Schema"""
    def __init__(self, message: str, errors: list[str], raw_output: str = ""):
        super().__init__(message, raw_output)
        self.errors = errors


class ApiError(IntentError):
    """通义千问 API 调用失败"""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


# ── 意图理解引擎 ──

class IntentEngine:
    """
    AI 意图理解引擎。

    将用户自然语言视频编辑指令解析为符合 schema/workflow.json 的结构化工作流。
    支持素材库引用：AI 在生成工作流时用 asset_id 引用用户已上传的素材。

    使用方式：
        engine = IntentEngine()
        assets = [{"id": "asset_001", "name": "钢铁侠", "type": "character", "path": "/assets/ironman.png"}]
        workflow = engine.process("把人物换成钢铁侠", assets=assets)
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化引擎。

        Args:
            api_key: 通义千问 API Key，默认从环境变量 DASHSCOPE_API_KEY 读取
        """
        self.api_key = api_key or settings.dashscope_api_key
        self.model = settings.intent_model
        self.temperature = settings.intent_temperature
        self.max_tokens = settings.intent_max_tokens
        self.max_retries = settings.intent_max_retries

        # 确保 Schema 已加载
        _ = schema_loader.schema

        if not self.api_key:
            logger.warning("DASHSCOPE_API_KEY 未配置，引擎将无法调用 AI")

    def process(self, user_input: str, assets: list | None = None,
                context: dict | None = None, project_id: str | None = None) -> dict:
        """
        处理用户输入，返回工作流 JSON。

        Args:
            user_input: 用户自然语言指令，如"把画面中的人物换成钢铁侠，背景改成火星"
            assets: 当前项目的素材列表（用户已上传），格式：
                [{"id": "asset_001", "name": "钢铁侠战甲", "type": "character", "path": "/assets/ironman.png"}]
                AI 只负责引用，不负责管理素材库。
            context: 可选上下文，如 {"project_name": "test", "resolution": "4k"}
            project_id: 可选项目 ID

        Returns:
            dict: 符合 schema/workflow.json 的完整工作流 JSON

        Raises:
            IntentError: 意图理解失败
            SchemaValidationError: AI 输出不符合 Schema
            ApiError: API 调用失败
        """
        if not user_input or not user_input.strip():
            raise IntentError("用户输入为空")

        asset_count = len(assets) if assets else 0
        logger.info(
            f"收到意图理解请求: '{user_input[:100]}{'...' if len(user_input) > 100 else ''}' "
            f"(素材: {asset_count} 个, 项目: {project_id or 'N/A'})"
        )

        if not self.api_key:
            raise ApiError("DASHSCOPE_API_KEY 未配置，请设置环境变量 DASHSCOPE_API_KEY")

        # 构建 prompt
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(user_input, context, assets)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_output = ""
        retry_count = 0

        while retry_count <= self.max_retries:
            try:
                # ── 调用通义千问 VL-Pro ──
                response = Generation.call(
                    api_key=self.api_key,
                    model=self.model,
                    messages=messages,
                    result_format="message",
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

                if response.status_code != 200:
                    raise ApiError(
                        f"API 调用失败 (HTTP {response.status_code}): {response.message}",
                        status_code=response.status_code,
                    )

                raw_output = response.output.choices[0].message.content
                logger.debug(f"AI 原始输出 ({len(raw_output)} 字符)")

                # ── 解析 JSON ──
                parsed = self._parse_json(raw_output)

                # ── 注入元数据 ──
                parsed = self._inject_metadata(parsed, user_input, project_id)

                # ── 验证 asset_id 合法性 ──
                asset_errors = self._validate_asset_refs(parsed, assets or [])
                if asset_errors:
                    logger.warning(f"素材引用验证问题: {asset_errors}")
                    # 自动修正非法的 asset_id（设为 null）
                    parsed = self._sanitize_asset_refs(parsed, assets or [])

                # ── 验证 Schema ──
                validation_errors = schema_loader.validate(parsed)
                if not validation_errors:
                    logger.info(
                        f"意图理解成功: '{parsed.get('understood', '')}' "
                        f"({len(parsed.get('steps', []))} 个步骤, "
                        f"{sum(1 for s in parsed.get('steps', []) if s.get('params', {}).get('asset_id'))} 个素材引用)"
                    )
                    return parsed

                # ── 验证失败，尝试修正 ──
                if retry_count < self.max_retries:
                    logger.warning(
                        f"Schema 验证失败 ({len(validation_errors)} 个错误)，"
                        f"第 {retry_count + 1}/{self.max_retries} 次重试"
                    )
                    for err in validation_errors[:5]:
                        logger.warning(f"  - {err}")

                    correction = build_correction_prompt(raw_output, validation_errors)
                    messages.append({"role": "assistant", "content": raw_output})
                    messages.append({"role": "user", "content": correction})
                else:
                    raise SchemaValidationError(
                        f"AI 输出不符合 Schema（{len(validation_errors)} 个错误，已重试 {self.max_retries} 次）",
                        errors=validation_errors,
                        raw_output=raw_output,
                    )

                retry_count += 1

            except ApiError:
                raise
            except SchemaValidationError:
                raise
            except json.JSONDecodeError as e:
                if retry_count < self.max_retries:
                    logger.warning(f"JSON 解析失败，第 {retry_count + 1}/{self.max_retries} 次重试: {e}")
                    correction = f"你的上一次输出不是合法 JSON。请确保输出纯 JSON 格式，不要包含 markdown 代码块标记。\n\n错误: {e.msg}"
                    messages.append({"role": "assistant", "content": raw_output})
                    messages.append({"role": "user", "content": correction})
                    retry_count += 1
                else:
                    raise IntentError(
                        f"AI 输出 JSON 解析失败（已重试 {self.max_retries} 次）: {e.msg}",
                        raw_output=raw_output,
                    )
            except Exception as e:
                raise IntentError(f"意图理解失败: {str(e)}", raw_output=raw_output)

        raise IntentError("意图理解失败，原因未知")

    # ── 私有方法 ──

    def _parse_json(self, raw_output: str) -> dict:
        """
        解析 AI 输出的 JSON。

        处理常见格式问题：
        - markdown 代码块标记 (```json ... ```)
        - 前导/尾随空白
        - BOM 字符
        - AI 在前面加了说明文字
        """
        text = raw_output.strip()

        if text.startswith("\ufeff"):
            text = text[1:]

        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]

        text = text.strip()

        if not text.startswith("{"):
            brace_start = text.find("{")
            if brace_start != -1:
                brace_end = text.rfind("}")
                if brace_end != -1:
                    text = text[brace_start:brace_end + 1]

        return json.loads(text)

    def _inject_metadata(self, parsed: dict, user_input: str,
                         project_id: str | None = None) -> dict:
        """
        注入/修正元数据字段。

        确保 version、workflow_id、created_at 等字段存在且正确。
        """
        if "version" not in parsed:
            parsed["version"] = "1.0"

        if "workflow_id" not in parsed or not parsed["workflow_id"]:
            parsed["workflow_id"] = str(uuid.uuid4())

        if "created_at" not in parsed:
            parsed["created_at"] = datetime.now(timezone.utc).isoformat()

        if project_id and "project_id" not in parsed:
            parsed["project_id"] = project_id

        for i, step in enumerate(parsed.get("steps", [])):
            if "id" not in step or not step["id"]:
                step["id"] = f"step_{i + 1}"

        return parsed

    def _validate_asset_refs(self, workflow: dict, assets: list) -> list[str]:
        """
        验证工作流中的 asset_id 引用是否合法。

        检查所有 replace 步骤中的 asset_id：
        - 不能引用不存在的 asset_id
        - 如果 asset_id 不为 null，必须存在于素材库中

        Returns:
            list[str]: 问题列表，空列表表示完全合法
        """
        valid_ids = {a["id"] for a in assets}
        issues = []

        for step in workflow.get("steps", []):
            if step.get("action") != "replace":
                continue

            params = step.get("params", {})
            asset_id = params.get("asset_id")

            if asset_id is not None and asset_id not in valid_ids:
                issues.append(
                    f"步骤 '{step.get('id', '?')}' 引用了不存在的 asset_id: '{asset_id}'"
                )

        return issues

    def _sanitize_asset_refs(self, workflow: dict, assets: list) -> dict:
        """
        自动修正非法的 asset_id 引用。

        将不存在的 asset_id 设为 null，并设置 requires_download=true。
        """
        valid_ids = {a["id"] for a in assets}

        for step in workflow.get("steps", []):
            if step.get("action") != "replace":
                continue

            params = step.get("params", {})
            asset_id = params.get("asset_id")

            if asset_id is not None and asset_id not in valid_ids:
                logger.warning(
                    f"修复非法 asset_id: '{asset_id}' → null "
                    f"(步骤: {step.get('id', '?')})"
                )
                params["asset_id"] = None
                params["requires_download"] = True
                params["missing_asset"] = params.get("source", str(asset_id))

        return workflow


# ── 全局引擎实例 ──
engine = IntentEngine()