import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import query_operator_skill

logger = logging.getLogger(__name__)

def register_operator_skill_tool(mcp, app):
    @mcp.tool(description="获取干员技能数据（默认第1个技能，等级10）。不生成图片。")
    async def get_operator_skill(
        operator_name: Annotated[str, Field(description="干员名")],
        operator_name_prefix: Annotated[str, Field(description="干员名的前缀，没有则为空")] = "",
        index: Annotated[int, Field(description="技能序号，从1开始")] = 1,
        level: Annotated[int, Field(description="技能等级 1~10（8~10为专精一/二/三）")] = 10,
    ) -> dict:
        tool_name = "get_operator_skill"
        started_at = log_tool_start(
            logger,
            tool_name,
            operator_name=operator_name,
            operator_name_prefix=operator_name_prefix,
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
            result = await query_operator_skill(
                context,
                operator_name=operator_name,
                operator_name_prefix=operator_name_prefix,
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
                operator_name=operator_name,
                operator_name_prefix=operator_name_prefix,
                index=index,
                level=level,
            )
            raise



