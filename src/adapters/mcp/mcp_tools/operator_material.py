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
请先调用 search 进行模糊搜索，再把返回的 id 传给本工具。

返回值同时携带：
- card_image_url / image_path：材料卡片图片（含精英化、技能通用升级、专精三大区块）；
- data：材料的结构化数据（中文键名）。
1–2 星干员无需材料升级，会返回友好提示 message。

注意：除非用户指明了需要精确的某项材料数据，否则在用户要求查询干员材料时应当优先，并且只向用户展示 card_image_url 所指示的图片，里面包含了更加丰富的信息。
"""


def register_operator_material_tool(mcp, app):
    @mcp.tool(description=_MATERIAL_TOOL_DESC)
    async def get_operator_material(
        operator_id: Annotated[str, Field(description='干员ID，可先调用 search 获取')],
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
            # AI-CORRECTION 2026-08-13: 上述注释部分失效——返回不再完全原样，
            # 图片 URL 字段由 image_url 更名为 card_image_url（对齐干员详情工具契约）。
            # AI-CORRECTION 2026-08-13: 上述订正亦失效——字段改名已下沉至 QueryExecutionResult.to_response()
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
