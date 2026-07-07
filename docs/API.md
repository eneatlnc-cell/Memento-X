# Memento-X Cloud API

Base URL: `http://localhost:8000/api/v1`

## 认证

所有 API 请求需携带 JWT token：

```
Authorization: Bearer <token>
```

## 端点

### POST /intent/understand

AI 意图理解 — 核心 API

**请求：**
```json
{
  "input": "把这个人换成钢铁侠，背景改成火星",
  "context": null,
  "project_id": null
}
```

**响应：**
```json
{
  "success": true,
  "understood": "把视频中的人物替换为钢铁侠，背景替换为火星",
  "workflow": {
    "steps": [
      {
        "action": "matting",
        "target": "person",
        "params": {},
        "reason": "抠出人物"
      },
      {
        "action": "replace",
        "target": "person",
        "params": {"prompt": "钢铁侠战衣"},
        "reason": "替换人物"
      },
      {
        "action": "composite",
        "params": {"format": "h264", "resolution": "4k"},
        "reason": "合成最终视频"
      }
    ],
    "estimated_duration_seconds": 90
  }
}
```

### POST /intent/status

回传工作流执行状态

### POST /account/register

用户注册

### POST /account/login

用户登录

### GET /health

健康检查