import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.operator_queries import query_operator_basic_by_id

logger = logging.getLogger(__name__)


_DATA_TOOL_DESC = """根据干员 ID 获取干员的结构化数据（属性、分类、技能数据等），以及一张包含上述全部数据的精美展示卡URL。
请先调用 search 进行模糊搜索，再把返回的 id 传给本工具。

注意：除非用户指明了需要精确的某项属性数据（如"攻击力是多少"），
否则在用户要求查询干员时应当优先，并且只向用户展示 card_image_url 所指示的图片，里面包含了更加丰富的信息。
"""

# AI-REMOVED 2026-08-13:
# Reason: get_operator_card 工具已按用户要求移除，其图片输出并入 get_operator_basic_data（card_image_url）。
# Trigger: MCP 工具说明重构需求（合并卡片与详情工具、URL 字段改名）。
# Evidence: app.py 中对应 import 与注册调用同步移除；工具总数由 8 减为 7。
# Replacement: get_operator_basic_data 返回 card_image_url（由原 image_url 重命名）。
# Risk: Low。Human Review: Required。
#
# Original code:
# _CARD_TOOL_DESC = """根据干员 ID 获取干员的图片卡片 URL。
# 请先调用 search 进行模糊搜索，再把返回的 id 传给本工具。
#
# 用户要求查询干员时，应优先使用本工具，向用户展示干员卡片图片。
# """


def register_operator_basic_data_tool(mcp, app):
    @mcp.tool(description=_DATA_TOOL_DESC)
    async def get_operator_basic_data(
        operator_id: Annotated[str, Field(description='干员ID，可先调用 search 获取')],
    ) -> dict:
        tool_name = "get_operator_basic_data"
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
            result = await query_operator_basic_by_id(
                context,
                operator_id=operator_id,
            )
            result_payload = result.to_response()
            # 仅返回结构化数据，去掉图片 URL
            # AI-CORRECTION 2026-08-13: 上述注释已失效——独立工具 get_operator_card 已移除，
            # 其图片输出并入本工具，image_url 字段重命名为 card_image_url 一并返回，不再删除。
            # AI-CORRECTION 2026-08-13: 上述订正亦失效——字段改名已下沉至 QueryExecutionResult.to_response()
            # （统一输出 card_image_url，CLI/MCP 共用），本工具不再需要字段重命名。
            # AI-REMOVED 2026-08-13:
            # Reason: 改名逻辑下沉底层后冗余，if 条件恒为 False。
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
                operator_id=operator_id,
            )
            raise


# AI-REMOVED 2026-08-13:
# Reason: get_operator_card 工具已按用户要求移除，其图片输出并入 get_operator_basic_data（card_image_url）。
# Trigger: MCP 工具说明重构需求（合并卡片与详情工具、URL 字段改名）。
# Evidence: 用户明确要求移除该工具；app.py 注册处同步删除；e2e 测试类 TestGetOperatorCard 同步归档。
# Replacement: register_operator_basic_data_tool 内的 get_operator_basic_data 返回 card_image_url。
# Risk: Low。Human Review: Required。
#
# Original code:
# def register_operator_card_tool(mcp, app):
#     @mcp.tool(description=_CARD_TOOL_DESC)
#     async def get_operator_card(
#         operator_id: Annotated[str, Field(description='干员ID，可先调用 search 获取')],
#     ) -> dict:
#         tool_name = "get_operator_card"
#         started_at = log_tool_start(
#             logger,
#             tool_name,
#             operator_id=operator_id,
#         )
#
#         try:
#             if not getattr(app.state, "ctx", None):
#                 log_tool_not_ready(logger, tool_name)
#                 result_payload = {"message": "未初始化数据上下文"}
#                 log_tool_end(logger, tool_name, started_at, result_payload)
#                 return result_payload
#
#             context: AppContext = app.state.ctx
#             result = await query_operator_basic_by_id(
#                 context,
#                 operator_id=operator_id,
#             )
#             result_payload = result.to_response()
#             # 仅返回图片 URL
#             image_url = result_payload.get("image_url")
#             if image_url:
#                 result_payload = {"image_url": image_url}
#             else:
#                 result_payload = {"image_url": None, "message": "未生成干员卡片图片"}
#             log_tool_end(logger, tool_name, started_at, result_payload)
#             return result_payload
#         except Exception:
#             log_tool_exception(
#                 logger,
#                 tool_name,
#                 started_at,
#                 operator_id=operator_id,
#             )
#             raise
