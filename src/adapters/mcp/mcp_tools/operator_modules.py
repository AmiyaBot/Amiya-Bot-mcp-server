import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import query_operator_modules_by_id

logger = logging.getLogger(__name__)


_OPERATOR_MODULES_TOOL_DESC = """根据干员 ID 获取该干员的全部模组，包括解锁条件、任务、三级属性与效果、升级材料，并返回模组卡片 URL。
请先调用 search 获取干员 id，再把 operator_id 传给本工具。

注意：除非用户指明需要精确的某项模组数据，否则查询干员模组时应优先且只展示 card_image_url 指向的模组卡片；卡片生成失败时再使用 data 中的结构化数据。
"""


def register_operator_modules_tool(mcp, app):
    @mcp.tool(description=_OPERATOR_MODULES_TOOL_DESC)
    async def get_operator_modules(
        operator_id: Annotated[str, Field(description="干员ID，可先调用 search 获取")],
    ) -> dict:
        tool_name = "get_operator_modules"
        started_at = log_tool_start(logger, tool_name, operator_id=operator_id)

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            result = await query_operator_modules_by_id(context, operator_id=operator_id)
            result_payload = result.to_response()
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(logger, tool_name, started_at, operator_id=operator_id)
            raise
