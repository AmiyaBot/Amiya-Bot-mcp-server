import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import query_operator_basic_by_id

logger = logging.getLogger(__name__)

tool_description = """根据干员 ID 获取干员的基础信息和属性，同时附带一张干员立绘图片。
请先调用 search_operator 进行模糊搜索，再把返回的 id 传给本工具。

Args:
    operator_id (str): 干员 ID，由 search_operator 返回

Returns:
    str: 一个Json对象，语义化的结构化干员信息包含在data字段中，图片的URL包含在image_url字段中。
    请尽可能向用户展示这张图片，无论用户是否明确需要图片资料。
"""


def register_operator_basic_tool(mcp, app):
    @mcp.tool(description=tool_description)
    async def get_operator_basic(
        operator_id: Annotated[str, Field(description='干员ID，可先调用 search_operator 获取')],
    ) -> dict:
        tool_name = "get_operator_basic"
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
            result = await query_operator_basic_by_id(
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
