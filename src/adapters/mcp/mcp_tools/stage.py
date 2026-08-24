from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.stage_queries import query_stage_by_id

logger = logging.getLogger(__name__)

_STAGE_TOOL_DESC = """根据关卡 ID 获取关卡结构化数据、地图、敌方单位、掉落详情和关卡卡片。
请先调用 search 获取 type 为「关卡」的候选条目，再把返回的 id 传给本工具。

返回 data、card_image_url，以及可选的 data_url；卡片生成失败时仍会返回结构化关卡数据。"""


def register_stage_tool(mcp, app):
    @mcp.tool(description=_STAGE_TOOL_DESC)
    async def get_stage_data(
        stage_id: Annotated[str, Field(description="关卡 ID，可先调用 search 获取（type 为「关卡」的条目 id）")],
    ) -> dict:
        tool_name = "get_stage_data"
        started_at = log_tool_start(logger, tool_name, stage_id=stage_id)

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            result_payload = (await query_stage_by_id(context, stage_id)).to_response()
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(logger, tool_name, started_at, stage_id=stage_id)
            raise
