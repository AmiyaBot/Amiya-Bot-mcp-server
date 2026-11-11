import logging
from typing import Annotated
from pydantic import Field
from src.app.services.autochess_strategy_queries import query_autochess_strategy_detail
from src.adapters.mcp.tool_logging import log_tool_start, log_tool_end, log_tool_exception

logger = logging.getLogger(__name__)


def register_autochess_strategy_tool(mcp, app):
    @mcp.tool(description='查询当期卫戍协议策略的发起人、完整说明、主动或被动技能及解锁条件，返回大展示卡 card_image_url。先通过 search 获取卫戍协议策略 ID；向用户展示返回的卡片。')
    async def get_autochess_strategy_detail(strategy_id: Annotated[str, Field(description='search 返回的卫戍协议策略 ID')]) -> dict:
        started = log_tool_start(logger, 'get_autochess_strategy_detail', strategy_id=strategy_id)
        try:
            if not getattr(app.state, 'ctx', None):
                payload = {'message': '未初始化数据上下文'}
            else:
                payload = (await query_autochess_strategy_detail(app.state.ctx, strategy_id)).to_response()
            log_tool_end(logger, 'get_autochess_strategy_detail', started, payload)
            return payload
        except Exception:
            log_tool_exception(logger, 'get_autochess_strategy_detail', started, strategy_id=strategy_id)
            raise
