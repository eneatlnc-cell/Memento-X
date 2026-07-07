# Memento-X 工作流 Schema 文档

## 概述

Memento-X 工作流 JSON 是云端 AI 意图理解引擎与本地调度器之间的核心接口契约。

- **云端输出**：AI 将用户自然语言解析为此格式
- **本地输入**：调度器按此格式解析并执行工具调用

## 设计原则

| 原则 | 说明 |
|------|------|
| 确定性 | 相同输入 → 相同输出。所有工具调用参数化，无随机性（除 seed 外） |
| 可组合性 | 多步骤通过 `depends_on` 建立依赖 DAG，支持并行和串行执行 |
| 可追溯性 | 每步有唯一 `id` + `reason` 字段，记录 AI 决策逻辑 |
| 可调试性 | JSON 人类可读，可直接手工编辑和 diff |

## 10 种工具一览

| # | action | 工具 | 说明 | 核心参数 |
|---|--------|------|------|----------|
| 1 | `matting` | 抠图 | 分离人物/物体与背景 | threshold, model, refine_edge |
| 2 | `track` | 追踪 | 视频帧序列遮罩追踪 | fps, mode, propagate |
| 3 | `replace` | 替换 | 替换画面中的主体/背景 | source, style, blend_strength |
| 4 | `composite` | 合成 | 多图层合成为一帧 | layers, blend_mode, output_fps |
| 5 | `effect` | 特效 | 火焰/粒子/光效等 | type, intensity, position |
| 6 | `color` | 调色 | 色彩校正/风格迁移 | style, brightness, contrast, saturation |
| 7 | `subtitle` | 字幕 | 文字标题/字幕 | text, style, font_size, color |
| 8 | `render` | 渲染 | HTML/SVG/Markdown → 图片/视频 | source, source_type, format, width, height |
| 9 | `crop` | 裁剪 | 画面裁剪/缩放 | aspect, resolution, position |
| 10 | `export` | 导出 | 最终输出成片 | format, quality, resolution, bitrate |

## 步骤通用字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 步骤唯一标识，如 `step_1`、`matting_person` |
| `action` | string | ✅ | 工具类型，必须是 10 种之一 |
| `target` | string | ✅ | 操作目标：person/background/object/scene/all 等 |
| `params` | object | ✅ | 工具参数，结构因 action 而异 |
| `depends_on` | string[] | ❌ | 依赖的前置步骤 ID 列表 |
| `fallback` | object | ❌ | 失败时的降级方案 |
| `reason` | string | ❌ | AI 解释为什么需要这一步 |

## 依赖关系

步骤之间通过 `depends_on` 建立 DAG：

```
step_1: matting ──────────────┐
                              ├── step_3: replace (person)
                              │         │
step_2: (无依赖)               │         │
                              │         │
          ┌───────────────────┘         │
          │                             │
          ▼                             ▼
    step_4: replace (bg)         step_5: composite
                                        │
                                        ▼
                                  step_6: export
```

- 无依赖的步骤可以并行执行
- `depends_on: []` 或省略表示无依赖
- 调度器按 `steps` 数组顺序提交，但通过 `depends_on` 控制实际执行顺序

## 各工具 params 详细说明

### 1. matting（抠图）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `threshold` | number | 0.5 | 置信度阈值 (0.0-1.0) |
| `refine_edge` | boolean | true | 边缘细化 |
| `output_format` | string | "png" | png/webp/matte |
| `model` | string | "auto" | birefnet/sam2/auto |
| `dilate_px` | integer | 0 | 遮罩膨胀像素 (-10~20) |
| `blur_px` | integer | 2 | 边缘模糊像素 (0~10) |

### 2. track（追踪）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `fps` | integer | 24 | 追踪帧率 |
| `mode` | string | "mask" | mask/point/box |
| `propagate` | boolean | true | 双向传播 |
| `max_gap_frames` | integer | 10 | 最大回溯帧数 |
| `confidence_threshold` | number | 0.7 | 置信度阈值 |

### 3. replace（替换）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `source` | string | - | 替换源描述 |
| `style` | string | "cinematic" | cinematic/anime/realistic 等 |
| `reference_image` | string | "" | 参考图路径 |
| `blend_strength` | number | 0.95 | 融合强度 |
| `preserve_lighting` | boolean | true | 保留光照 |
| `scale_mode` | string | "auto" | fit/fill/stretch/auto |

### 4. composite（合成）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `layers` | array | [] | 图层列表（含 source/blend_mode/opacity/position） |
| `blend_mode` | string | "normal" | 全局混合模式 |
| `output_fps` | integer | 24 | 输出帧率 |
| `resolution` | string | "source" | 4k/1080p/720p/source |
| `anti_alias` | boolean | true | 抗锯齿 |

### 5. effect（特效）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | "particle" | fire/particle/glow/transition/lightning/smoke/water/magic |
| `intensity` | number | 0.7 | 强度 (0.0-1.0) |
| `position` | string | "full" | top/bottom/center/full/left/right |
| `duration_frames` | integer | 0 | 持续帧数 (0=全程) |
| `start_frame` | integer | 0 | 起始帧 |
| `color` | string | "#ff6600" | 主色调 hex |
| `seed` | integer | 42 | 随机种子（确定性） |

### 6. color（调色）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `style` | string | "cinematic" | cinematic/warm/cool/vintage/noir/pastel/vivid/custom |
| `lut` | string | "" | 自定义 LUT 路径 |
| `brightness` | number | 0.0 | 亮度 (-1.0~1.0) |
| `contrast` | number | 1.0 | 对比度 (0.0~3.0) |
| `saturation` | number | 1.0 | 饱和度 (0.0~3.0) |
| `temperature` | number | 0.0 | 色温 (-1.0~1.0) |
| `shadows` | number | 0.0 | 阴影 (-1.0~1.0) |
| `highlights` | number | 0.0 | 高光 (-1.0~1.0) |

### 7. subtitle（字幕）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `text` | string | - | 字幕文本 |
| `style` | string | "bottom" | bottom/top/karaoke/title/caption/custom |
| `font_size` | integer | 36 | 字体大小 (px) |
| `font_family` | string | "sans-serif" | 字体名称 |
| `color` | string | "#ffffff" | 文字颜色 hex |
| `outline_color` | string | "#000000" | 描边颜色 hex |
| `outline_width` | integer | 2 | 描边宽度 (px) |
| `background` | string | "" | 背景色 hex |
| `start_frame` | integer | 0 | 出现帧 |
| `end_frame` | integer | 0 | 消失帧 |
| `alignment` | string | "center" | left/center/right |

### 8. render（渲染）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `source` | string | - | HTML/SVG/Markdown 内容或路径 |
| `source_type` | string | "html" | html/svg/markdown/file |
| `format` | string | "png" | png/jpg/webp/mp4/webm/gif |
| `width` | integer | 1920 | 渲染宽度 (px) |
| `height` | integer | 1080 | 渲染高度 (px) |
| `fps` | integer | 24 | 视频帧率 |
| `duration_seconds` | number | 3.0 | 视频时长 |
| `background` | string | "#00000000" | 背景色 |
| `quality` | integer | 90 | 质量 (1-100) |

### 9. crop（裁剪）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `aspect` | string | "16:9" | 目标宽高比 |
| `resolution` | string | "source" | 4k/1080p/720p/source |
| `x` | integer | 0 | 起始 X |
| `y` | integer | 0 | 起始 Y |
| `width` | integer | 0 | 宽度 (0=自动) |
| `height` | integer | 0 | 高度 (0=自动) |
| `position` | string | "center" | 锚点位置 |
| `scale_filter` | string | "lanczos" | lanczos/bilinear/bicubic/nearest |

### 10. export（导出）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `format` | string | "h264" | prores/h264/h265/dnxhd/gif/image_sequence |
| `quality` | string | "high" | lossless/high/medium/low |
| `resolution` | string | "source" | 4k/1080p/720p/source |
| `bitrate` | string | "" | 目标码率 (50M/10M) |
| `output_path` | string | "" | 输出路径 |
| `include_audio` | boolean | true | 包含音频 |
| `audio_bitrate` | string | "256k" | 音频码率 |
| `color_space` | string | "rec709" | rec709/rec2020/srgb/display_p3 |
| `max_file_size_mb` | integer | 0 | 最大文件大小 (0=不限制) |

## 版本

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-07-07 | 初始版本，10种工具，完整 params 定义 |

## 相关文件

- `schema/workflow.json` — JSON Schema Draft-07 正式定义
- `docs/WORKFLOW_EXAMPLES.md` — 完整工作流示例
- `cloud/intent/schema.py` — Python 类型定义
- `local/scheduler/executor.py` — 调度器实现