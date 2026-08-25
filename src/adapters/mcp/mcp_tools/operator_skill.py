import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import query_operator_skill_by_id

logger = logging.getLogger(__name__)

def register_operator_skill_tool(mcp, app):
    @mcp.tool(
        description=(
            "根据干员 ID 一次性获取该干员的完整技能列表及每个技能实际可用的全部等级数据；普通等级按游戏内1~7显示，"
            "支持专精的技能还会返回专精一、专精二、专精三。"
            "需要完整技能列表或对比不同技能等级时请调用本工具；请先调用 search 获取 id。本工具不生成图片。"
        )
    )
    async def get_operator_skill(
        operator_id: Annotated[str, Field(description="干员ID，可先调用 search 获取")],
    ) -> dict:
        tool_name = "get_operator_skill"
        started_at = log_tool_start(
            logger,
            tool_name,
            operator_id=operator_id,
        )

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            result = await query_operator_skill_by_id(
                context,
                operator_id=operator_id,
            )
            result_payload = result.to_response()
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(
                logger,
                tool_name,
                started_at,
                operator_id=operator_id,
            )
            raise

