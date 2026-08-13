import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import query_operator_material_by_id

logger = logging.getLogger(__name__)

_MATERIAL_TOOL_DESC = """根据干员 ID 获取干员精英化与技能升级所需的材料数据。
请先调用 search_operator 进行模糊搜索，再把返回的 id 传给本工具。

返回值同时携带：
- image_url / image_path：材料卡片图片（含精英化、技能通用升级、专精三大区块）；
- data：材料的结构化数据（中文键名）。
1–2 星干员无需材料升级，会返回友好提示 message。
"""


def register_operator_material_tool(mcp, app):
    @mcp.tool(description=_MATERIAL_TOOL_DESC)
    async def get_operator_material(
        operator_id: Annotated[str, Field(description='干员ID，可先调用 search_operator 获取')],
    ) -> dict:
        tool_name = "get_operator_material"
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
            result = await query_operator_material_by_id(
                context,
                operator_id=operator_id,
            )
            # 材料页面的图片与结构化数据都是主输出，原样返回完整响应
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
