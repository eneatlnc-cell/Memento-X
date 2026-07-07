"""意图理解 API 路由"""
import logging
from fastapi import APIRouter, HTTPException, Depends

from cloud.intent.schema import IntentRequest, IntentResponse
from cloud.intent.engine import (
    engine,
    IntentError,
    SchemaValidationError,
    ApiError,
)
from cloud.account.auth import get_current_user
from cloud.account.quota import check_quota, consume_quota

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/understand", response_model=IntentResponse)
async def understand_intent(
    request: IntentRequest,
    user_id: str = Depends(get_current_user),
):
    """
    核心 API：将用户自然语言输入解析为结构化工作流。

    这是 Memento-X 唯一需要 AI 调用的环节。
    输入：用户自然语言 + 素材库引用
    输出：JSON 工作流（步骤序列），符合 schema/workflow.json v1.0

    素材库处理：
    - AI 在生成工作流时用 asset_id 引用已有素材
    - 如果素材库中没有匹配，AI 标记 requires_download=true
    - AI 不负责素材管理，只负责引用
    """
    # 检查配额
    if not await check_quota(user_id):
        raise HTTPException(status_code=429, detail="今日配额已用完，请升级订阅")

    # 将 Pydantic AssetRef 列表转为 dict 列表
    assets = None
    if request.assets:
        assets = [a.model_dump() for a in request.assets]

    try:
        workflow = engine.process(
            user_input=request.input,
            assets=assets,
            context=request.context,
            project_id=request.project_id,
        )

        # 消耗配额
        await consume_quota(user_id)

        return IntentResponse(
            success=True,
            understood=workflow.get("understood", ""),
            workflow=workflow,
        )

    except SchemaValidationError as e:
        logger.error(f"Schema 验证失败: {e}")
        return IntentResponse(
            success=False,
            error=f"AI 输出不符合 Schema: {str(e)}",
            validation_errors=e.errors,
            raw_output=e.raw_output,
        )

    except ApiError as e:
        logger.error(f"API 调用失败: {e}")
        return IntentResponse(
            success=False,
            error=f"API 调用失败: {str(e)}",
        )

    except IntentError as e:
        logger.error(f"意图理解失败: {e}")
        return IntentResponse(
            success=False,
            error=f"意图理解失败: {str(e)}",
            raw_output=e.raw_output,
        )

    except Exception as e:
        logger.exception("意图理解未知错误")
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


@router.post("/status", response_model=dict)
async def report_status(status: dict, user_id: str = Depends(get_current_user)):
    """
    本地调度器回传工作流执行状态。
    用于云端监控和用量统计。
    """
    logger.info(f"收到状态回传: workflow_id={status.get('workflow_id')}, status={status.get('status')}")
    return {"received": True, "workflow_id": status.get("workflow_id")}