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


_DATA_TOOL_DESC = """根据干员 ID 获取干员的结构化数据（属性、分类、技能数据等）。
请先调用 search 进行模糊搜索，再把返回的 id 传给本工具。

注意：除非用户指明了需要精确的某项属性数据（如"攻击力是多少"），
否则在用户要求查询干员时应当使用 get_operator_card 并返回图片。
"""

_CARD_TOOL_DESC = """根据干员 ID 获取干员的图片卡片 URL。
请先调用 search 进行模糊搜索，再把返回的 id 传给本工具。

用户要求查询干员时，应优先使用本工具，向用户展示干员卡片图片。
"""


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
            if "image_url" in result_payload:
                del result_payload["image_url"]
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


def register_operator_card_tool(mcp, app):
    @mcp.tool(description=_CARD_TOOL_DESC)
    async def get_operator_card(
        operator_id: Annotated[str, Field(description='干员ID，可先调用 search 获取')],
    ) -> dict:
        tool_name = "get_operator_card"
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
            # 仅返回图片 URL
            image_url = result_payload.get("image_url")
            if image_url:
                result_payload = {"image_url": image_url}
            else:
                result_payload = {"image_url": None, "message": "未生成干员卡片图片"}
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
