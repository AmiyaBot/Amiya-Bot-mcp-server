import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import query_operator_skins

logger = logging.getLogger(__name__)

_OPERATOR_SKINS_TOOL_DESC = """根据干员 ID 获取该干员的皮肤列表（皮肤名、系列、画师、台词、获取方式等）与每个皮肤的立绘卡片图片 URL。
请先调用 search 获取干员 id（type 为「干员」或「皮肤」的条目均可取得 operator_id），再把 operator_id 传给本工具。

注意：除非用户指明了需要精确的某项皮肤数据，否则在用户要求查询干员皮肤时应当优先，并且只向用户展示各皮肤条目 card_url 所指示的图片，里面包含了更加丰富的信息。"""


def register_operator_skins_tool(mcp, app):
    @mcp.tool(description=_OPERATOR_SKINS_TOOL_DESC)
    async def get_operator_skins(
        operator_id: Annotated[str, Field(description="干员ID，可先调用 search 获取（type 为「干员」的条目 id，或「皮肤」条目的 operator_id）")],
    ) -> dict:
        tool_name = "get_operator_skins"
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
            result = await query_operator_skins(
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
