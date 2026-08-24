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

_OPERATOR_SKINS_TOOL_DESC = """根据干员 ID 获取皮肤选择卡、皮肤列表（皮肤名、系列、画师、台词、获取方式等），以及每个皮肤各自的详情卡和立绘原图 URL。
请先调用 search 获取干员 id（type 为「干员」或「皮肤」的条目均可取得 operator_id），再把 operator_id 传给本工具。

展示规则：首次响应应优先且只展示顶层 card_image_url 所指向的皮肤选择卡，不要一次展示 skins 中的多张大图。选择卡带有序号；用户选定序号或皮肤名后，再展示对应条目的 card_url（资料卡）或立绘URL（原图）。如果选择卡生成失败，才使用结构化列表进行文本选择。"""


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
