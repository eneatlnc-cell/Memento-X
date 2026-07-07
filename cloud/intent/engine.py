"""
Memento-X 意图理解引擎

核心链路：
用户输入 → engine.process() → 调用通义千问VL-Pro → 解析JSON → 验证Schema → 返回工作流JSON

这是 Memento-X 唯一需要 AI 参与的环节。
AI 只做意图理解，后续所有像素级工作由本地确定性工具完成。
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

    使用方式：
        engine = IntentEngine()
        workflow = engine.process("把人物换成钢铁侠")
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

    def process(self, user_input: str, context: dict | None = None) -> dict:
        """
        处理用户输入，返回工作流 JSON。

        Args:
            user_input: 用户自然语言指令，如"把画面中的人物换成钢铁侠，背景改成火星"
            context: 可选上下文，如 {"project_name": "test", "resolution": "4k"}

        Returns:
            dict: 符合 schema/workflow.json 的完整工作流 JSON

        Raises:
            IntentError: 意图理解失败
            SchemaValidationError: AI 输出不符合 Schema
            ApiError: API 调用失败
        """
        if not user_input or not user_input.strip():
            raise IntentError("用户输入为空")

        logger.info(f"收到意图理解请求: '{user_input[:100]}{'...' if len(user_input) > 100 else ''}'")

        if not self.api_key:
            raise ApiError("DASHSCOPE_API_KEY 未配置，请设置环境变量 DASHSCOPE_API_KEY")

        # 构建 prompt
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(user_input, context)

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
                parsed = self._inject_metadata(parsed, user_input)

                # ── 验证 Schema ──
                validation_errors = schema_loader.validate(parsed)
                if not validation_errors:
                    logger.info(
                        f"意图理解成功: '{parsed.get('understood', '')}' "
                        f"({len(parsed.get('steps', []))} 个步骤)"
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

                    # 构建修正 prompt
                    correction = build_correction_prompt(raw_output, validation_errors)
                    messages.append({"role": "assistant", "content": raw_output})
                    messages.append({"role": "user", "content": correction})
                else:
                    # 重试次数用完
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

        # 不应该到这里
        raise IntentError("意图理解失败，原因未知")

    def _parse_json(self, raw_output: str) -> dict:
        """
        解析 AI 输出的 JSON。

        处理常见格式问题：
        - markdown 代码块标记 (```json ... ```)
        - 前导/尾随空白
        - BOM 字符
        """
        text = raw_output.strip()

        # 移除 BOM
        if text.startswith("\ufeff"):
            text = text[1:]

        # 移除 markdown 代码块标记
        if text.startswith("```"):
            # 找到第一个换行后的内容
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]
            # 移除结尾的 ```
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]

        text = text.strip()

        # 如果 AI 在前面加了说明文字，尝试提取 JSON 部分
        if not text.startswith("{"):
            brace_start = text.find("{")
            if brace_start != -1:
                brace_end = text.rfind("}")
                if brace_end != -1:
                    text = text[brace_start:brace_end + 1]

        return json.loads(text)

    def _inject_metadata(self, parsed: dict, user_input: str) -> dict:
        """
        注入/修正元数据字段。

        确保 version、workflow_id、created_at 等字段存在且正确。
        """
        # version
        if "version" not in parsed:
            parsed["version"] = "1.0"

        # workflow_id（UUID v4）
        if "workflow_id" not in parsed or not parsed["workflow_id"]:
            parsed["workflow_id"] = str(uuid.uuid4())

        # created_at
        if "created_at" not in parsed:
            parsed["created_at"] = datetime.now(timezone.utc).isoformat()

        # 确保每个 step 有 id
        for i, step in enumerate(parsed.get("steps", [])):
            if "id" not in step or not step["id"]:
                step["id"] = f"step_{i + 1}"

        return parsed


# ── 全局引擎实例 ──
engine = IntentEngine()