"""
Memento-X 意图理解 Prompt 模板

动态构建 System Prompt 和 User Prompt，
工具列表和参数约束从 schema/workflow.json 自动提取。

素材库引用：
- 用户已上传的素材通过 assets 参数注入 User Prompt
- AI 在生成工作流时用 asset_id 引用已有素材
- AI 不负责素材管理（创建/修改/删除），只负责"引用"
"""
import json
from cloud.intent.schema_loader import schema_loader


def _build_tool_table() -> str:
    """从 Schema 动态生成工具列表（Markdown 表格）"""
    tool_names = schema_loader.get_tool_names()
    if not tool_names:
        return "（Schema 未加载，无可用工具）"

    name_map = {
        "matting": "抠图", "track": "追踪", "replace": "替换",
        "composite": "合成", "effect": "特效", "color": "调色",
        "subtitle": "字幕", "render": "渲染", "crop": "裁剪", "export": "导出",
    }

    lines = ["| action | 工具 | 说明 | 关键参数 |",
             "|--------|------|------|----------|"]

    for tool in tool_names:
        label = name_map.get(tool, tool)
        params_def = schema_loader.get_tool_params(tool)
        props = params_def.get("properties", {})

        key_params = []
        for pname, pdef in list(props.items())[:4]:
            default = pdef.get("default", "")
            key_params.append(f"{pname}={default}" if default else pname)

        param_str = ", ".join(key_params) if key_params else "—"
        desc = params_def.get("title", tool)
        lines.append(f"| {tool} | {label} | {desc} | {param_str} |")

    return "\n".join(lines)


def _build_tool_params_detail() -> str:
    """为每个工具生成详细的参数说明"""
    tool_names = schema_loader.get_tool_names()
    if not tool_names:
        return ""

    sections = []
    for tool in tool_names:
        params_def = schema_loader.get_tool_params(tool)
        props = params_def.get("properties", {})

        if not props:
            continue

        lines = [f"\n### {tool}"]
        lines.append("| 参数 | 类型 | 默认值 | 说明 |")
        lines.append("|------|------|--------|------|")

        for pname, pdef in props.items():
            ptype = pdef.get("type", "string")
            default = pdef.get("default", "—")
            desc = pdef.get("description", "")
            enum_vals = pdef.get("enum")
            if enum_vals:
                desc += f"（可选: {', '.join(str(v) for v in enum_vals)}）"
            lines.append(f"| {pname} | {ptype} | {default} | {desc} |")

        sections.append("\n".join(lines))

    return "\n".join(sections)


def _build_asset_library_rules() -> str:
    """构建素材库引用规则"""
    return """## 素材库引用规则

用户可能已经上传了一些素材。每个素材有唯一 asset_id。
当用户指令中提到某个角色/场景/物体时，你需要：
1. 检查素材库中是否有匹配项（通过名称、类型匹配）
2. 有匹配 → 在 replace 步骤的 params 中使用 asset_id 引用
3. 无匹配 → 在 params 中设置 "asset_id": null, "requires_download": true, "missing_asset": "素材名称"

### asset_id 的正确使用
- 如果素材库中有"钢铁侠战甲"（asset_001），用户说"换成钢铁侠" → 设置 asset_id: "asset_001"
- 如果素材库中没有匹配 → 设置 asset_id: null, requires_download: true

### 你的边界
- ✅ 你能做：读取素材列表 → 匹配用户指令 → 在输出中使用 asset_id
- ❌ 你不能做：添加素材、删除素材、修改素材路径、捏造不存在的 asset_id
- 不允许使用任何不在素材列表中的 asset_id"""


def build_system_prompt() -> str:
    """
    构建 System Prompt。

    动态从 schema/workflow.json 读取工具列表和参数约束，
    确保 AI 输出严格符合 Schema。
    """
    tool_table = _build_tool_table()
    target_values = schema_loader.get_target_values()
    tool_names = schema_loader.get_tool_names()
    asset_rules = _build_asset_library_rules()

    return f"""你是 Memento-X 的视频编辑 AI 意图理解引擎。你的唯一职责是将用户的自然语言视频编辑需求解析为结构化 JSON 工作流。

## 可用工具（共 {len(tool_names)} 种）

{tool_table}

{asset_rules}

## 步骤通用字段

每个步骤必须包含以下字段：
- id: string — 步骤唯一标识，如 "step_1"、"matting_person"。后续步骤通过 depends_on 引用。
- action: string — 工具名称，必须是 {json.dumps(tool_names, ensure_ascii=False)}
- target: string — 操作目标，必须是 {json.dumps(target_values, ensure_ascii=False)}
- params: object — 工具参数（见下方详细说明）
- depends_on: string[] — 依赖的前置步骤 ID 列表（可选，无依赖则省略）
- reason: string — 简短解释为什么需要这一步

## 输出格式

你必须严格输出以下 JSON 格式，不要包含任何 markdown 代码块标记（不要 ```json），不要包含任何其他文字：

{{
  "version": "1.0",
  "workflow_id": "自动生成 UUID",
  "understood": "你对用户意图的简短理解（中文，50字以内）",
  "steps": [
    {{
      "id": "step_1",
      "action": "matting",
      "target": "person",
      "params": {{}},
      "reason": "抠出人物为替换做准备"
    }}
  ]
}}

## 工作流编排规则

1. 始终以 export 步骤结束（除非用户只要求裁剪/调色等中间操作）
2. 人物替换必须包含：matting → replace（如需追踪则加入 track）
3. 背景替换可以与人物抠图并行（depends_on 都指向 step_1 的抠图结果）
4. 特效（effect）和调色（color）在合成（composite）之后
5. 字幕（subtitle）在调色之后
6. 裁剪（crop）在合成之前
7. 渲染（render）独立执行，通过 composite 的 layers 合成
8. depends_on 建立 DAG，无依赖的步骤可以并行执行
9. 不要添加任何工具列表中没有的操作
10. 步骤数量控制在 3-12 个之间

## 输出前检查

- [ ] version 必须是 "1.0"
- [ ] workflow_id 是有效的 UUID v4 格式（如 550e8400-e29b-41d4-a716-446655440001）
- [ ] 每个 step 的 action 在可用工具列表中
- [ ] 每个 step 的 target 在允许值列表中
- [ ] depends_on 引用的 id 必须存在于前面的步骤中
- [ ] 最后一步是 export（除非用户明确不要导出）
- [ ] replace 步骤正确使用了 asset_id 或 requires_download
- [ ] 输出是纯 JSON，不含 markdown 标记"""


def build_user_prompt(user_input: str, context: dict | None = None,
                      assets: list | None = None) -> str:
    """
    构建 User Prompt。

    Args:
        user_input: 用户自然语言指令
        context: 可选的上下文信息
        assets: 可选的素材列表，格式：
            [{"id": "asset_001", "name": "钢铁侠战甲", "type": "character", "path": "/assets/ironman.png"}]
    """
    parts = []

    # ── 素材库 ──
    if assets:
        parts.append("## 用户已上传的素材库")
        parts.append("以下素材已经由用户上传到本地，你可以通过 asset_id 引用它们：")
        parts.append("")
        parts.append("| asset_id | 名称 | 类型 | 文件路径 |")
        parts.append("|----------|------|------|----------|")
        for a in assets:
            aid = a.get("id", "?")
            name = a.get("name", "?")
            atype = a.get("type", "?")
            path = a.get("path", "?")
            parts.append(f"| {aid} | {name} | {atype} | {path} |")
        parts.append("")
        parts.append("**重要**：如果用户指令中提到的角色/场景/物体在素材库中有匹配，你必须在 replace 步骤的 params 中使用对应的 asset_id。")
        parts.append("如果素材库中没有匹配，设置 asset_id: null, requires_download: true, missing_asset: 用户需要的素材名称。")
        parts.append("")

    # ── 上下文 ──
    if context:
        parts.append("## 上下文信息")
        if context.get("project_name"):
            parts.append(f"项目名称: {context['project_name']}")
        if context.get("resolution"):
            parts.append(f"目标分辨率: {context['resolution']}")
        if context.get("duration"):
            parts.append(f"视频时长: {context['duration']}")
        if context.get("available_tools"):
            parts.append(f"已安装工具: {', '.join(context['available_tools'])}")
        parts.append("")

    # ── 用户指令 ──
    parts.append("## 用户指令")
    parts.append(user_input)
    parts.append("")
    parts.append("请输出工作流 JSON：")

    return "\n".join(parts)


def build_correction_prompt(original_output: str, validation_errors: list[str]) -> str:
    """
    构建修正 Prompt（验证失败时使用）。

    Args:
        original_output: AI 上次的原始输出
        validation_errors: jsonschema 验证错误列表
    """
    errors_text = "\n".join(f"- {e}" for e in validation_errors[:10])

    return f"""你的上一次输出不符合 Schema 规范，请修正以下错误后重新输出。

## 错误列表

{errors_text}

## 你的上一次输出

{original_output}

## 修正要求

1. 只修正错误，不要改变工作流逻辑
2. 确保输出是纯 JSON，不含 markdown 标记
3. 确保所有字段名和值符合 Schema 约束
4. 确保 asset_id 是素材库中存在的 ID，或为 null

请输出修正后的工作流 JSON："""