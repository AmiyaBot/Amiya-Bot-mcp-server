from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.enemy_queries import query_enemy_by_id

logger = logging.getLogger(__name__)

_ENEMY_TOOL_DESC = """根据敌人 ID 获取敌人基础资料、能力、等级属性、控制免疫、关联单位和敌人卡片。
请先调用 search 获取 type 为「敌人」的候选条目，再把返回的 id 传给本工具。

返回 data、card_image_url，以及可选的 data_url；卡片生成失败时仍会返回结构化敌人数据。除非用户明确要求某项精确属性，否则应优先展示 card_image_url 指向的卡片。"""


def register_enemy_tool(mcp, app):
    @mcp.tool(description=_ENEMY_TOOL_DESC)
    async def get_enemy_data(
        enemy_id: Annotated[str, Field(description="敌人 ID，可先调用 search 获取（type 为「敌人」的条目 id）")],
    ) -> dict:
        tool_name = "get_enemy_data"
        started_at = log_tool_start(logger, tool_name, enemy_id=enemy_id)

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            result_payload = (await query_enemy_by_id(context, enemy_id)).to_response()
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(logger, tool_name, started_at, enemy_id=enemy_id)
            raise

