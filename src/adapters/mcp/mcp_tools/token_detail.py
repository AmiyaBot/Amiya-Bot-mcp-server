import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import query_token_detail_by_id

logger = logging.getLogger(__name__)

_TOKEN_DETAIL_TOOL_DESC = """根据召唤物 ID 获取召唤物的详情数据（名称、属性、天赋、技能、所属干员等）与召唤物卡片图片。
请先调用 search 获取候选召唤物的 id（type 为「召唤物」的条目），再把返回的 id 传给本工具。

注意：除非用户指明了需要精确的某项属性数据，否则在用户要求查询召唤物时应当优先，并且只向用户展示 card_image_url 所指示的图片，里面包含了更加丰富的信息。"""


def register_token_detail_tool(mcp, app):
    @mcp.tool(description=_TOKEN_DETAIL_TOOL_DESC)
    async def get_token_detail(
        token_id: Annotated[str, Field(description="召唤物ID，可先调用 search 获取（type 为「召唤物」的条目 id）")],
    ) -> dict:
        tool_name = "get_token_detail"
        started_at = log_tool_start(
            logger,
            tool_name,
            token_id=token_id,
        )

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            result = await query_token_detail_by_id(
                context,
                token_id=token_id,
            )
            result_payload = result.to_response()
            # 图片 URL 字段由 image_url 更名为 card_image_url（2026-08-13，对齐干员详情工具契约）
            # AI-CORRECTION 2026-08-13: 上述注释失效——字段改名已下沉至 QueryExecutionResult.to_response()
            # （统一输出 card_image_url，CLI/MCP 共用），本工具不再需要字段重命名。
            # AI-REMOVED 2026-08-13:
            # Reason: 改名逻辑下沉底层后冗余。
            # Trigger: CLI 侧统一字段契约需求。
            # Evidence: QueryExecutionResult.to_response() 已直接输出 card_image_url。
            # Replacement: QueryExecutionResult.to_response()。
            # Risk: Low。Human Review: Required。
            #
            # Original code:
            # if "image_url" in result_payload:
            #     result_payload["card_image_url"] = result_payload.pop("image_url")
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(
                logger,
                tool_name,
                started_at,
                token_id=token_id,
            )
            raise
