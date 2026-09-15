from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.integrated_strategy_item_queries import (
    query_integrated_strategy_item_by_id,
)


logger = logging.getLogger(__name__)

_ITEM_TOOL_DESC = """根据唯一 ID 获取集成战略藏品或主题机制道具详情和卡片。
请先调用 search，从「集成战略藏品」「剧目」「骰子」「密文板」「构想」「通宝」「零件」候选中选择唯一条目，再把其 id 传给本工具；不要把名称直接传入。

剧目的普通/猩红版本、骰子的使用场景和通宝的品相会作为 variants 合并返回；通宝和零件会通过 sub_type 标明分类。"""


def register_integrated_strategy_item_tool(mcp, app):
    @mcp.tool(description=_ITEM_TOOL_DESC)
    async def get_integrated_strategy_item_detail(
        item_id: Annotated[
            str,
            Field(
                description=(
                    "集成战略藏品或机制道具的唯一代表 ID，必须使用 "
                    "search 返回条目的 id"
                )
            ),
        ],
    ) -> dict:
        tool_name = "get_integrated_strategy_item_detail"
        started_at = log_tool_start(logger, tool_name, item_id=item_id)

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            result_payload = (
                await query_integrated_strategy_item_by_id(context, item_id)
            ).to_response()
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(
                logger,
                tool_name,
                started_at,
                item_id=item_id,
            )
            raise
