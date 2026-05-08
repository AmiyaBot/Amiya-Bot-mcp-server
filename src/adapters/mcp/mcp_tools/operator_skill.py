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
    @mcp.tool(description="根据干员 ID 获取干员技能数据（默认第1个技能，等级10）。请先调用 search_operator 获取 id。本工具不生成图片。")
    async def get_operator_skill(
        operator_id: Annotated[str, Field(description="干员ID，可先调用 search_operator 获取")],
        index: Annotated[int, Field(description="技能序号，从1开始")] = 1,
        level: Annotated[int, Field(description="技能等级 1~10（8~10为专精一/二/三）")] = 10,
    ) -> dict:
        tool_name = "get_operator_skill"
        started_at = log_tool_start(
            logger,
            tool_name,
            operator_id=operator_id,
            index=index,
            level=level,
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
                index=index,
                level=level,
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
                index=index,
                level=level,
            )
            raise




