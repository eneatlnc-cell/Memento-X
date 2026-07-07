# 工作流 Schema 定义

Memento-X 云端 AI 意图理解引擎输出的标准化 JSON 指令格式。

## 工作流示例

### 示例 1：人物替换

```json
{
  "understood": "把视频中的人物替换为钢铁侠，背景替换为火星",
  "steps": [
    {
      "action": "matting",
      "target": "person",
      "params": {},
      "reason": "抠出人物，准备替换"
    },
    {
      "action": "tracking",
      "target": "mask",
      "params": {"fps": 24},
      "reason": "追踪人物遮罩，确保逐帧准确"
    },
    {
      "action": "replace",
      "target": "person",
      "params": {"prompt": "钢铁侠战衣，电影级画质"},
      "reason": "替换人物为钢铁侠"
    },
    {
      "action": "replace",
      "target": "background",
      "params": {"prompt": "火星表面，红色沙漠，科幻感"},
      "reason": "替换背景为火星"
    },
    {
      "action": "composite",
      "params": {"format": "prores", "resolution": "4k"},
      "reason": "合成所有图层为最终视频"
    }
  ]
}
```

### 示例 2：调色

```json
{
  "understood": "给视频添加电影感暖色调",
  "steps": [
    {
      "action": "color_grade",
      "params": {"style": "cinematic"},
      "reason": "应用电影级调色"
    }
  ]
}
```

### 示例 3：裁剪 + 字幕

```json
{
  "understood": "裁剪为竖屏并添加字幕",
  "steps": [
    {
      "action": "crop",
      "params": {"aspect": "9:16", "resolution": "1080p"},
      "reason": "裁剪为竖屏比例"
    },
    {
      "action": "subtitle",
      "params": {"text": "精彩瞬间", "style": "bottom"},
      "reason": "添加底部字幕"
    }
  ]
}
```

## 可用工具

| 工具 | action | 说明 | 参数 |
|------|--------|------|------|
| 抠图 | matting | 高精度人物/物体分离 | target: person/object/foreground |
| 追踪 | tracking | 视频帧级遮罩追踪 | fps: 24/30 |
| 替换 | replace | 替换人物/背景/物体 | target, prompt |
| 合成 | composite | 合成最终视频 | format: prores/h264, resolution: 4k/1080p |
| 调色 | color_grade | 专业调色 | style: cinematic/warm/cool/vintage |
| 字幕 | subtitle | 字幕/标题 | text, style: bottom/karaoke |
| 特效 | effect | 粒子/火焰/光效 | type: fire/particle/glow |
| 裁剪 | crop | 视频裁剪 | aspect: 16:9/9:16/1:1 |
| 防抖 | stabilize | 视频防抖 | strength: light/medium/strong |
| 降噪 | denoise | 视频降噪 | strength: light/medium/strong |