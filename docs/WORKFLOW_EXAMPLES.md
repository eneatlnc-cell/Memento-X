# Memento-X 工作流示例

## 用户输入 → 工作流映射

### 人物替换
```
输入: "把这个人换成钢铁侠，背景改成火星"
输出: matting(person) → tracking(mask) → replace(person, ironman) → replace(background, mars) → composite(4k)
```

### 调色
```
输入: "调成电影感暖色调"
输出: color_grade(cinematic)
```

### 裁剪
```
输入: "裁剪成竖屏"
输出: crop(9:16, 1080p)
```

### 字幕
```
输入: "加上字幕：你好世界"
输出: subtitle("你好世界", bottom)
```

### 特效
```
输入: "加火焰特效"
输出: effect(fire)
```

### 组合操作
```
输入: "把视频防抖，然后调成电影色调，最后加字幕：精彩瞬间"
输出: stabilize(medium) → color_grade(cinematic) → subtitle("精彩瞬间", bottom)
```

### 完整流程
```
输入: "把人物抠出来，背景换成星空，加粒子特效，最后合成4K输出"
输出: matting(person) → tracking(mask) → replace(background, "星空，银河") → effect(particle) → composite(prores, 4k)
```

## 成本估算

| 操作 | 预估耗时 | 费用 |
|------|---------|------|
| 意图理解 | < 1 秒 | ~0.01-0.05 元 |
| 抠图 (BiRefNet) | 5-15 秒 | 0 元 |
| 追踪 (SAM2) | 30-120 秒 | 0 元 |
| 替换 (ComfyUI) | 30-120 秒 | 0 元 |
| 合成 (FFmpeg) | 10-60 秒 | 0 元 |
| 调色 (DaVinci) | 5-30 秒 | 0 元 |
| **总计** | **2-5 分钟** | **~0.01-0.05 元** |