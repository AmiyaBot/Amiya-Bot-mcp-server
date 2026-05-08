import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import search_operator as search_operator_query

logger = logging.getLogger(__name__)


def register_operator_search_tool(mcp, app):
    @mcp.tool(description="按干员名称进行模糊搜索，返回候选干员的 name 和 id。拿到 id 后，再调用 get_operator_basic 或 get_operator_skill。")
    async def search_operator(
        query: Annotated[str, Field(description="干员名称关键词，支持模糊搜索")],
    ) -> dict:
        tool_name = "search_operator"
        started_at = log_tool_start(
            logger,
            tool_name,
            query=query,
        )

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            result = search_operator_query(
                context,
                query=query,
            )
            result_payload = result.to_response()
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(
                logger,
                tool_name,
                started_at,
                query=query,
            )
            raise