"""Memento-X 云端入口 — FastAPI 服务"""
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from cloud.config import settings
from cloud.api.intent import router as intent_router
from cloud.api.account import router as account_router
from cloud.api.workflow import router as workflow_router
from cloud.api.status import router as status_router
from cloud.api.notification import router as notification_router
from cloud.api.dataset import router as dataset_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# ── 生命周期管理 ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期。

    startup: 启动调度器、PushService 后台任务，绑定依赖
    shutdown: 优雅停止所有后台任务
    """
    # ── startup ──
    from cloud.services.scheduler import task_scheduler
    from cloud.services.push import push_service
    from cloud.services.dispatch import dispatch_service
    from cloud.db.engine import init_db

    # 数据库初始化（自动建表）
    try:
        await init_db()
        logger.info("数据库连接成功，表已就绪")
    except Exception as e:
        logger.warning(f"数据库初始化跳过（未配置 PostgreSQL）: {e}")

    # 绑定依赖：调度器 ← 推送服务
    task_scheduler.bind_push(push_service.push_status)

    # 启动后台任务
    await task_scheduler.start()
    await push_service.start()

    logger.info("Memento-X Cloud v0.2.0 已启动")
    logger.info(f"  端点: http://{settings.host}:{settings.port}")
    logger.info(f"  调度器: 队列 worker + 心跳监控 (30s) + 主动轮询")
    logger.info(f"  PushService: 连接清理循环 (30s ping, 90s ttl)")
    logger.info(f"  数据库: PostgreSQL (asyncpg)")

    yield

    # ── shutdown ──
    logger.info("正在关闭 Memento-X Cloud...")
    await task_scheduler.stop()
    await push_service.stop()
    logger.info("Memento-X Cloud 已关闭")


app = FastAPI(
    title="Memento-X Cloud",
    description="AI 意图理解 + 任务调度 + 账号系统 — AI 只做意图理解，像素级工作全部由本地确定性工具完成",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(intent_router, prefix="/api/v1/intent", tags=["intent"])
app.include_router(account_router, prefix="/api/v1/account", tags=["account"])
app.include_router(workflow_router, prefix="/api/v1/workflow", tags=["workflow"])
app.include_router(status_router, prefix="/api/v1/status", tags=["status"])
app.include_router(notification_router, prefix="/api/v1/notification", tags=["notification"])
app.include_router(dataset_router, prefix="/api/v1/dataset", tags=["dataset"])


@app.get("/", response_class=HTMLResponse)
async def root():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memento-X Cloud</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;background:#0a0a0f;color:#e0e0e0;display:flex;justify-content:center;align-items:center;min-height:100vh}
.container{background:#12121a;border:1px solid #1e1e2a;border-radius:12px;padding:40px;width:400px;max-width:90vw}
h1{text-align:center;font-size:1.5rem;margin-bottom:4px}
.sub{text-align:center;color:#777;font-size:0.85rem;margin-bottom:24px}
.tabs{display:flex;gap:0;margin-bottom:20px;border-bottom:2px solid #1e1e2a}
.tab{flex:1;text-align:center;padding:10px;cursor:pointer;color:#777;font-size:0.9rem;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .2s}
.tab.active{color:#00d4aa;border-bottom-color:#00d4aa}
label{display:block;font-size:0.8rem;color:#777;margin-bottom:4px;margin-top:12px}
input{width:100%;padding:10px 12px;background:#0d0d14;border:1px solid #1e1e2a;border-radius:6px;color:#e0e0e0;font-size:0.9rem;outline:none}
input:focus{border-color:#00d4aa}
.btn{width:100%;padding:12px;margin-top:16px;background:#00d4aa;color:#0a0a0f;border:none;border-radius:6px;font-size:0.95rem;font-weight:600;cursor:pointer;transition:opacity .2s}
.btn:hover{opacity:0.85}
.result{margin-top:16px;padding:12px;background:#0d0d14;border:1px solid #1e1e2a;border-radius:6px;font-size:0.8rem;word-break:break-all;display:none}
.result.show{display:block}
.result .token{color:#00d4aa;font-family:monospace;font-size:0.85rem}
.error{color:#e04040;margin-top:8px;font-size:0.8rem;display:none}
</style>
</head>
<body>
<div class="container">
<h1>Memento-X Cloud</h1>
<p class="sub">v0.2.0 · 注册获取 Token</p>
<div class="tabs">
<div class="tab active" onclick="switchTab('login')">登录</div>
<div class="tab" onclick="switchTab('register')">注册</div>
</div>
<form id="loginForm" onsubmit="login(event)">
<label>邮箱</label>
<input id="loginEmail" type="email" required>
<label>密码</label>
<input id="loginPassword" type="password" required>
<button class="btn" type="submit">登录</button>
</form>
<form id="registerForm" style="display:none" onsubmit="register(event)">
<label>邮箱</label>
<input id="regEmail" type="email" required>
<label>密码</label>
<input id="regPassword" type="password" required minlength="6">
<button class="btn" type="submit">注册</button>
</form>
<div class="error" id="error"></div>
<div class="result" id="result">
<p style="color:#777;margin-bottom:4px">Token（复制后用于 GPU 启动器）</p>
<div class="token" id="tokenText"></div>
</div>
</div>
<script>
function switchTab(t){document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));document.querySelector('.tab:nth-child('+(t==='login'?1:2)+')').classList.add('active');document.getElementById('loginForm').style.display=t==='login'?'block':'none';document.getElementById('registerForm').style.display=t==='register'?'block':'none';document.getElementById('error').style.display='none'}
async function login(e){e.preventDefault();const email=document.getElementById('loginEmail').value;const password=document.getElementById('loginPassword').value;
try{const r=await fetch('/api/v1/account/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});const d=await r.json();
if(r.ok){document.getElementById('tokenText').textContent=d.access_token;document.getElementById('result').classList.add('show');document.getElementById('error').style.display='none'}
else{document.getElementById('error').textContent=d.detail||'登录失败';document.getElementById('error').style.display='block'}}catch(err){document.getElementById('error').textContent='网络错误';document.getElementById('error').style.display='block'}}
async function register(e){e.preventDefault();const email=document.getElementById('regEmail').value;const password=document.getElementById('regPassword').value;
try{const r=await fetch('/api/v1/account/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});const d=await r.json();
if(r.ok){document.getElementById('tokenText').textContent=d.access_token;document.getElementById('result').classList.add('show');document.getElementById('error').style.display='none';switchTab('login')}
else{document.getElementById('error').textContent=d.detail||'注册失败';document.getElementById('error').style.display='block'}}catch(err){document.getElementById('error').textContent='网络错误';document.getElementById('error').style.display='block'}}
</script>
</body>
</html>"""


@app.get("/health")
async def health():
    from cloud.services.scheduler import task_scheduler
    from cloud.services.push import push_service
    return {
        "status": "ok",
        "service": "Memento-X Cloud",
        "version": "0.2.0",
        "queue_size": task_scheduler.get_queue_size(),
        "ws_connections": push_service.get_connection_count(),
    }


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)