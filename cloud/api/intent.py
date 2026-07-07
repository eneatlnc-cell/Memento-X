"""意图理解 API 路由"""
from fastapi import APIRouter, HTTPException, Depends
from cloud.intent.schema import IntentRequest, IntentResponse, WorkflowStatus
from cloud.intent.engine import engine
from cloud.account.auth import get_current_user
from cloud.account.quota import check_quota, consume_quota

router = APIRouter()


@router.post("/understand", response_model=IntentResponse)
async def understand_intent(
    request: IntentRequest,
    user_id: str = Depends(get_current_user),
):
    """
    核心 API：将用户自然语言输入解析为结构化工作流。

    这是 Memento-X 唯一需要 AI 调用的环节。
    输入：用户自然语言（如"把这个人换成钢铁侠，背景改成火星"）
    输出：JSON 工作流（步骤序列）
    """
    # 检查配额
    if not await check_quota(user_id):
        raise HTTPException(status_code=429, detail="今日配额已用完，请升级订阅")

    response = await engine.understand(request.input, request.context)

    if response.success:
        await consume_quota(user_id)

    return response


@router.post("/status", response_model=dict)
async def report_status(
    status: WorkflowStatus,
    user_id: str = Depends(get_current_user),
):
    """
    本地调度器回传工作流执行状态。
    用于云端监控和用量统计。
    """
    # TODO: 持久化状态到数据库
    return {"received": True, "workflow_id": status.workflow_id}