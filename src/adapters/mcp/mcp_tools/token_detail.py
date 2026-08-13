import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import query_token_detail_by_id

logger = logging.getLogger(__name__)

_TOKEN_DETAIL_TOOL_DESC = """根据召唤物 ID 获取召唤物的详情数据（名称、属性、天赋、技能、所属干员等）与召唤物卡片图片。
请先调用 search 获取候选召唤物的 id（type 为「召唤物」的条目），再把返回的 id 传给本工具。"""


def register_token_detail_tool(mcp, app):
    @mcp.tool(description=_TOKEN_DETAIL_TOOL_DESC)
    async def get_token_detail(
        token_id: Annotated[str, Field(description="召唤物ID，可先调用 search 获取（type 为「召唤物」的条目 id）")],
    ) -> dict:
        tool_name = "get_token_detail"
        started_at = log_tool_start(
            logger,
            tool_name,
            token_id=token_id,
        )

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            result = await query_token_detail_by_id(
                context,
                token_id=token_id,
            )
            result_payload = result.to_response()
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(
                logger,
                tool_name,
                started_at,
                token_id=token_id,
            )
            raise
