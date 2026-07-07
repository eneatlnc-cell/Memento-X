"""
Memento-X 意图理解引擎

唯一 AI 参与环节：将用户自然语言输入解析为结构化 JSON 工作流。
使用通义千问 VL-Pro 进行意图理解，输出标准化工作流指令。
"""
import json
from typing import Optional
from dashscope import Generation
from cloud.config import settings
from cloud.intent.schema import Workflow, WorkflowStep, IntentResponse


SYSTEM_PROMPT = """你是 Memento 视频编辑 AI 助手。你的唯一职责是将用户的自然语言视频编辑需求解析为结构化 JSON 工作流。

## 可用工具

| 工具 | 用途 | 参数 |
|------|------|------|
| matting | 抠图/人物分离 | target: "person" / "object" / "foreground" |
| tracking | 遮罩追踪 | target: "mask", fps: 24 |
| replace | 替换元素 | target: "person" / "background" / "object", with: 描述 |
| composite | 合成帧序列 | format: "prores" / "h264", resolution: "4k" / "1080p" |
| color_grade | 调色 | style: "cinematic" / "warm" / "cool" / "vintage" |
| subtitle | 添加字幕 | text: 字幕内容, style: "bottom" / "karaoke" |
| effect | 特效 | type: "fire" / "particle" / "glow" / "transition" |
| crop | 裁剪 | aspect: "16:9" / "9:16" / "1:1", resolution: "4k" / "1080p" |
| stabilize | 防抖 | strength: "light" / "medium" / "strong" |
| denoise | 降噪 | strength: "light" / "medium" / "strong" |

## 输出格式

必须严格输出以下 JSON 格式，不要包含任何其他文字：

{
  "understood": "你对用户意图的简短理解",
  "steps": [
    {"action": "工具名", "target": "目标", "params": {}, "reason": "为什么需要这一步"}
  ]
}

## 规则
1. 只在上述工具列表中选择 action
2. 步骤顺序必须合理（先抠图再替换再合成）
3. 如果用户需求涉及人物替换，必须包含 matting → tracking → replace → composite
4. 如果用户提到了特定风格，在 color_grade 中体现
5. 不要添加任何工具列表中没有的操作
6. 输出必须是合法 JSON，不要包含 markdown 代码块标记"""


class IntentEngine:
    """AI 意图理解引擎"""

    def __init__(self):
        self.api_key = settings.dashscope_api_key

    async def understand(self, user_input: str, context: Optional[str] = None) -> IntentResponse:
        """
        将用户自然语言输入解析为结构化工作流。

        Args:
            user_input: 用户自然语言输入
            context: 可选的上下文（如当前项目信息）

        Returns:
            IntentResponse: 包含理解结果和工作流步骤
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if context:
            messages.append({"role": "system", "content": f"当前项目上下文：{context}"})

        messages.append({"role": "user", "content": user_input})

        try:
            response = Generation.call(
                api_key=self.api_key,
                model="qwen-vl-pro",
                messages=messages,
                result_format="message",
                temperature=0.1,  # 低温度确保输出稳定
                max_tokens=2000,
            )

            if response.status_code != 200:
                return IntentResponse(
                    success=False,
                    error=f"API 调用失败: {response.message}",
                )

            raw_output = response.output.choices[0].message.content

            # 清理可能的 markdown 代码块标记
            raw_output = raw_output.strip()
            if raw_output.startswith("```"):
                raw_output = raw_output.split("\n", 1)[1]
                if raw_output.endswith("```"):
                    raw_output = raw_output[:-3]
                raw_output = raw_output.strip()

            parsed = json.loads(raw_output)

            steps = []
            for step_data in parsed.get("steps", []):
                steps.append(WorkflowStep(
                    action=step_data["action"],
                    target=step_data.get("target", ""),
                    params=step_data.get("params", {}),
                    reason=step_data.get("reason", ""),
                ))

            workflow = Workflow(
                steps=steps,
                estimated_duration_seconds=len(steps) * 30,  # 粗略估计每步 30 秒
            )

            return IntentResponse(
                success=True,
                understood=parsed.get("understood", ""),
                workflow=workflow,
            )

        except json.JSONDecodeError as e:
            return IntentResponse(
                success=False,
                error=f"AI 输出解析失败: {str(e)}",
                raw_output=raw_output if 'raw_output' in dir() else "",
            )
        except Exception as e:
            return IntentResponse(
                success=False,
                error=f"意图理解失败: {str(e)}",
            )


# 全局引擎实例
engine = IntentEngine()