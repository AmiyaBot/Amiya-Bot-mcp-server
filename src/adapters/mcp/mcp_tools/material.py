import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import query_material_by_id

logger = logging.getLogger(__name__)

_MATERIAL_TOOL_DESC = """根据材料 ID 获取材料详情、加工合成路线、官方关卡掉落信息和材料卡片。
请先调用 search 获取 type 为「材料」的候选条目，再把返回的 id 传给本工具。

数据全部来自本地明日方舟解包资源，不调用一图流；刷图效率推荐数据当前为空。返回 data、card_image_url，以及可选的 data_url。"""


def register_material_tool(mcp, app):
    @mcp.tool(description=_MATERIAL_TOOL_DESC)
    async def get_material(
        material_id: Annotated[str, Field(description="材料 ID，可先调用 search 获取（type 为「材料」的条目 id）")],
    ) -> dict:
        tool_name = "get_material"
        started_at = log_tool_start(logger, tool_name, material_id=material_id)

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            result_payload = (await query_material_by_id(context, material_id)).to_response()
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(logger, tool_name, started_at, material_id=material_id)
            raise
