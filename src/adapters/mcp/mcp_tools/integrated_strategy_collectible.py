from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.integrated_strategy_collectible_queries import (
    query_integrated_strategy_collectible_by_id,
)


logger = logging.getLogger(__name__)

_COLLECTIBLE_TOOL_DESC = """根据唯一的集成战略藏品 ID 获取藏品详情和详情卡片。
请先调用 search，由 AI 根据名称、所属主题和效果选择 type 为「集成战略藏品」的唯一候选，再把该候选的 id 传给本工具；不要把藏品名称直接传入。

返回 data、card_image_url，以及可选的 data_url / image_path；卡片生成失败时仍会返回结构化藏品数据。"""


def register_integrated_strategy_collectible_tool(mcp, app):
    @mcp.tool(description=_COLLECTIBLE_TOOL_DESC)
    async def get_integrated_strategy_collectible_detail(
        collectible_id: Annotated[
            str,
            Field(
                description=(
                    "集成战略藏品的唯一 ID，必须使用 search 返回的"
                    "「集成战略藏品」条目 id"
                )
            ),
        ],
    ) -> dict:
        tool_name = "get_integrated_strategy_collectible_detail"
        started_at = log_tool_start(
            logger,
            tool_name,
            collectible_id=collectible_id,
        )

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            result_payload = (
                await query_integrated_strategy_collectible_by_id(
                    context,
                    collectible_id,
                )
            ).to_response()
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(
                logger,
                tool_name,
                started_at,
                collectible_id=collectible_id,
            )
            raise
