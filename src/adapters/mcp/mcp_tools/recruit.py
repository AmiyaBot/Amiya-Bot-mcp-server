import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end, log_tool_exception, log_tool_not_ready, log_tool_start
from src.app.context import AppContext
from src.app.services.recruit_queries import query_recruit

logger = logging.getLogger(__name__)

_RECRUIT_TOOL_DESC = """根据文本中的明日方舟公开招募标签，返回可锁定的稀有干员组合与候选干员。
输入例如“高级资深干员、近卫、输出”或“资深 近战位”。仅支持文本标签，不进行 OCR；标签最多组合三项。"""


def register_recruit_tool(mcp, app):
    @mcp.tool(description=_RECRUIT_TOOL_DESC)
    async def recruit(
        text: Annotated[str, Field(description="公招标签文本，例如：高级资深干员、近卫、输出")],
    ) -> dict:
        tool_name = "recruit"
        started_at = log_tool_start(logger, tool_name, text=text)
        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, payload)
                return payload
            context: AppContext = app.state.ctx
            payload = await query_recruit(context, text)
            log_tool_end(logger, tool_name, started_at, payload)
            return payload
        except Exception:
            log_tool_exception(logger, tool_name, started_at, text=text)
            raise
