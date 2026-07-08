# Memento-X 工作流示例

## 示例 1：简单替换（人物换钢铁侠 + 背景换火星 + 火焰特效）

用户输入："把画面中的人物换成钢铁侠，背景换成火星，并添加火焰特效"

```json
{
  "version": "1.0",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440001",
  "understood": "把视频中的人物替换为钢铁侠，背景替换为火星表面，底边添加火焰特效，最后导出4K ProRes成片",
  "created_at": "2026-07-07T10:00:00Z",
  "steps": [
    {
      "id": "step_1",
      "action": "scene_edit",
      "target": "person",
      "params": {
        "threshold": 0.5,
        "refine_edge": true,
        "output_format": "png",
        "model": "auto",
        "dilate_px": 0,
        "blur_px": 2
      },
      "reason": "提取人物结构化描述，带透明通道"
    },
    {
      "id": "step_2",
      "action": "replace",
      "target": "person",
      "params": {
        "source": "钢铁侠战衣，金属质感，红色和金色配色，电影级画质",
        "style": "cinematic",
        "blend_strength": 0.95,
        "preserve_lighting": true,
        "scale_mode": "auto"
      },
      "depends_on": ["step_1"],
      "reason": "将提取的人物替换为钢铁侠，保留原始光照阴影"
    },
    {
      "id": "step_3",
      "action": "replace",
      "target": "background",
      "params": {
        "source": "火星表面，红色沙漠，远处有山脉，科幻感天空",
        "style": "sci-fi",
        "blend_strength": 1.0,
        "preserve_lighting": false,
        "scale_mode": "fill"
      },
      "depends_on": ["step_1"],
      "reason": "将背景替换为火星场景，不需要保留原始背景光照"
    },
    {
      "id": "step_4",
      "action": "effect",
      "target": "scene",
      "params": {
        "type": "fire",
        "intensity": 0.8,
        "position": "bottom",
        "duration_frames": 0,
        "start_frame": 0,
        "color": "#ff6600",
        "seed": 42
      },
      "depends_on": ["step_2", "step_3"],
      "reason": "在画面底部添加火焰特效，增强科幻感"
    },
    {
      "id": "step_5",
      "action": "composite",
      "target": "all",
      "params": {
        "layers": [],
        "blend_mode": "normal",
        "output_fps": 24,
        "resolution": "4k",
        "anti_alias": true
      },
      "depends_on": ["step_4"],
      "reason": "合成所有图层，输出4K 24fps"
    },
    {
      "id": "step_6",
      "action": "export",
      "target": "all",
      "params": {
        "format": "prores",
        "quality": "high",
        "resolution": "source",
        "include_audio": true,
        "audio_bitrate": "256k",
        "color_space": "rec709"
      },
      "depends_on": ["step_5"],
      "reason": "导出为 ProRes 4K 成片，保留原始音频"
    }
  ]
}
```

**依赖 DAG：**
```
step_1 (scene_edit) ──┬── step_2 (replace person) ──┐
                      │                              ├── step_4 (effect) ── step_5 (composite) ── step_6 (export)
                      └── step_3 (replace bg) ───────┘
```

---

## 示例 2：多人物替换 + 风格调色

用户输入："把左边的人换成蜘蛛侠，右边的人换成奇异博士，调成电影感冷色调，加标题"

```json
{
  "version": "1.0",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440002",
  "understood": "将画面中两个人物分别替换为蜘蛛侠和奇异博士，应用电影感冷色调，添加标题字幕",
  "created_at": "2026-07-07T10:30:00Z",
  "steps": [
    {
      "id": "scene_edit_left",
      "action": "scene_edit",
      "target": "person",
      "params": {
        "threshold": 0.55,
        "refine_edge": true,
        "model": "birefnet",
        "dilate_px": 1,
        "blur_px": 2
      },
      "reason": "提取左侧人物结构化描述"
    },
    {
      "id": "scene_edit_right",
      "action": "scene_edit",
      "target": "person",
      "params": {
        "threshold": 0.55,
        "refine_edge": true,
        "model": "birefnet",
        "dilate_px": 1,
        "blur_px": 2
      },
      "reason": "提取右侧人物结构化描述，与左侧并行处理"
    },
    {
      "id": "replace_spiderman",
      "action": "replace",
      "target": "person",
      "params": {
        "source": "蜘蛛侠，经典红蓝战衣，漫威电影风格",
        "style": "cinematic",
        "blend_strength": 0.9,
        "preserve_lighting": true
      },
      "depends_on": ["scene_edit_left"],
      "reason": "替换左侧人物为蜘蛛侠"
    },
    {
      "id": "replace_strange",
      "action": "replace",
      "target": "person",
      "params": {
        "source": "奇异博士，红色斗篷，魔法光环，漫威电影风格",
        "style": "cinematic",
        "blend_strength": 0.9,
        "preserve_lighting": true
      },
      "depends_on": ["scene_edit_right"],
      "reason": "替换右侧人物为奇异博士"
    },
    {
      "id": "composite_chars",
      "action": "composite",
      "target": "all",
      "params": {
        "layers": [],
        "output_fps": 24,
        "resolution": "4k",
        "anti_alias": true
      },
      "depends_on": ["replace_spiderman", "replace_strange"],
      "reason": "合成两个替换后的人物"
    },
    {
      "id": "color_grade",
      "action": "color",
      "target": "all",
      "params": {
        "style": "cool",
        "brightness": 0.0,
        "contrast": 1.05,
        "saturation": 0.9,
        "temperature": -0.3,
        "shadows": 0.1,
        "highlights": -0.05
      },
      "depends_on": ["composite_chars"],
      "reason": "应用电影感冷色调"
    },
    {
      "id": "add_title",
      "action": "subtitle",
      "target": "all",
      "params": {
        "text": "LONDON — 3024",
        "style": "title",
        "font_size": 64,
        "font_family": "sans-serif",
        "color": "#ffffff",
        "outline_color": "#000000",
        "outline_width": 3,
        "alignment": "center",
        "start_frame": 0,
        "end_frame": 72
      },
      "depends_on": ["color_grade"],
      "reason": "在开头添加标题字幕，持续 3 秒（72帧@24fps）"
    },
    {
      "id": "export_final",
      "action": "export",
      "target": "all",
      "params": {
        "format": "h264",
        "quality": "high",
        "resolution": "4k",
        "bitrate": "50M",
        "include_audio": true,
        "color_space": "rec2020"
      },
      "depends_on": ["add_title"],
      "reason": "导出 4K H.264 成片，50Mbps 码率"
    }
  ]
}
```

**依赖 DAG：**
```
scene_edit_left ── replace_spiderman ──┐
                                       ├── composite_chars ── color_grade ── add_title ── export_final
scene_edit_right ── replace_strange ───┘
```

---

## 示例 3：竖屏裁剪 + 字幕 + 防抖

用户输入："把这个视频裁剪成竖屏，加字幕'精彩瞬间'，然后导出"

```json
{
  "version": "1.0",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440003",
  "understood": "将视频裁剪为9:16竖屏，添加底部字幕'精彩瞬间'，导出1080p H.264",
  "created_at": "2026-07-07T11:00:00Z",
  "steps": [
    {
      "id": "crop_vertical",
      "action": "crop",
      "target": "all",
      "params": {
        "aspect": "9:16",
        "resolution": "1080p",
        "position": "center",
        "scale_filter": "lanczos"
      },
      "reason": "裁剪为竖屏9:16比例，居中取景"
    },
    {
      "id": "add_subtitle",
      "action": "subtitle",
      "target": "all",
      "params": {
        "text": "精彩瞬间",
        "style": "bottom",
        "font_size": 42,
        "color": "#ffffff",
        "outline_color": "#000000",
        "outline_width": 2,
        "alignment": "center"
      },
      "depends_on": ["crop_vertical"],
      "reason": "添加底部字幕"
    },
    {
      "id": "export_vertical",
      "action": "export",
      "target": "all",
      "params": {
        "format": "h264",
        "quality": "high",
        "resolution": "1080p",
        "bitrate": "10M",
        "include_audio": true
      },
      "depends_on": ["add_subtitle"],
      "reason": "导出1080p竖屏H.264成片"
    }
  ]
}
```

---

## 示例 4：HTML 渲染 + 合成（动态标题动画）

用户输入："生成一个动态标题'SHOWTIME'，然后合成到视频开头"

```json
{
  "version": "1.0",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440004",
  "understood": "用HTML渲染一个动态标题动画，合成到视频开头作为片头",
  "created_at": "2026-07-07T11:30:00Z",
  "steps": [
    {
      "id": "render_title",
      "action": "render",
      "target": "scene",
      "params": {
        "source": "<div style='width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#1a1a2e,#16213e);'><h1 style='font-size:96px;color:#e94560;text-shadow:0 0 40px rgba(233,69,96,0.5);animation:fadeIn 1s ease-out;'>SHOWTIME</h1></div><style>@keyframes fadeIn{from{opacity:0;transform:scale(0.8)}to{opacity:1;transform:scale(1)}}</style>",
        "source_type": "html",
        "format": "mp4",
        "width": 1920,
        "height": 1080,
        "fps": 24,
        "duration_seconds": 3.0,
        "background": "#00000000",
        "quality": 95
      },
      "reason": "渲染3秒的HTML标题动画为透明背景MP4"
    },
    {
      "id": "composite_intro",
      "action": "composite",
      "target": "all",
      "params": {
        "layers": [
          {
            "source": "render_title",
            "blend_mode": "normal",
            "opacity": 1.0
          }
        ],
        "blend_mode": "normal",
        "output_fps": 24,
        "resolution": "4k",
        "anti_alias": true
      },
      "depends_on": ["render_title"],
      "reason": "将标题动画合成到视频开头"
    },
    {
      "id": "export_with_intro",
      "action": "export",
      "target": "all",
      "params": {
        "format": "h264",
        "quality": "high",
        "resolution": "4k",
        "bitrate": "50M",
        "include_audio": true
      },
      "depends_on": ["composite_intro"],
      "reason": "导出含片头动画的4K成片"
    }
  ]
}
```

---

## 示例 5：完整后期流程（场景编辑+追踪+替换+调色+字幕+导出）

用户输入："把主角换成超人，全程追踪，调成电影暖色调，加字幕'MAN OF STEEL'，导出4K ProRes"

```json
{
  "version": "1.0",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440005",
  "understood": "全程追踪主角并替换为超人，应用电影暖色调，添加底部字幕，导出4K ProRes",
  "created_at": "2026-07-07T12:00:00Z",
  "steps": [
    {
      "id": "scene_edit_hero",
      "action": "scene_edit",
      "target": "person",
      "params": {
        "threshold": 0.45,
        "refine_edge": true,
        "model": "sam2",
        "dilate_px": 0,
        "blur_px": 3
      },
      "reason": "用SAM2提取主角结构化描述（视频处理首选）"
    },
    {
      "id": "track_hero",
      "action": "track",
      "target": "mask",
      "params": {
        "fps": 24,
        "mode": "mask",
        "propagate": true,
        "max_gap_frames": 10,
        "confidence_threshold": 0.7
      },
      "depends_on": ["scene_edit_hero"],
      "reason": "对主角遮罩进行逐帧追踪"
    },
    {
      "id": "replace_superman",
      "action": "replace",
      "target": "person",
      "params": {
        "source": "超人，蓝色紧身衣，红色披风，S标志，亨利·卡维尔风格",
        "style": "cinematic",
        "blend_strength": 0.92,
        "preserve_lighting": true,
        "scale_mode": "auto"
      },
      "depends_on": ["track_hero"],
      "reason": "将追踪到的主角替换为超人，保留原始光照"
    },
    {
      "id": "color_warm",
      "action": "color",
      "target": "all",
      "params": {
        "style": "warm",
        "brightness": 0.02,
        "contrast": 1.1,
        "saturation": 1.15,
        "temperature": 0.25,
        "shadows": 0.05,
        "highlights": -0.05
      },
      "depends_on": ["replace_superman"],
      "reason": "应用电影暖色调，增强金色质感"
    },
    {
      "id": "subtitle_steel",
      "action": "subtitle",
      "target": "all",
      "params": {
        "text": "MAN OF STEEL",
        "style": "bottom",
        "font_size": 40,
        "font_family": "sans-serif",
        "color": "#ffd700",
        "outline_color": "#000000",
        "outline_width": 3,
        "alignment": "center",
        "start_frame": 0,
        "end_frame": 0
      },
      "depends_on": ["color_warm"],
      "reason": "添加金色底部字幕 'MAN OF STEEL'"
    },
    {
      "id": "export_4k",
      "action": "export",
      "target": "all",
      "params": {
        "format": "prores",
        "quality": "high",
        "resolution": "4k",
        "include_audio": true,
        "audio_bitrate": "256k",
        "color_space": "rec2020"
      },
      "depends_on": ["subtitle_steel"],
      "reason": "导出4K ProRes 422 HQ 成片"
    }
  ]
}
```

**依赖 DAG：**
```
scene_edit_hero ── track_hero ── replace_superman ── color_warm ── subtitle_steel ── export_4k
```

---

## 成本估算

| 示例 | 步骤数 | 预估耗时 | AI 费用 |
|------|--------|----------|---------|
| 简单替换 | 6 | 2-4 分钟 | ~0.02 元 |
| 多人物替换 | 8 | 3-6 分钟 | ~0.03 元 |
| 竖屏裁剪 | 3 | 30秒-1分钟 | ~0.01 元 |
| HTML渲染 | 3 | 30秒-1分钟 | ~0.01 元 |
| 完整后期 | 6 | 3-5 分钟 | ~0.02 元 |

所有像素级操作（SVG场景编辑/追踪/替换/特效/合成/调色/导出）均为本地确定性工具执行，0 元调用费。