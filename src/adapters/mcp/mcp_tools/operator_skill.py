import json
import logging
from typing import Annotated

from pydantic import Field

from src.app.context import AppContext
from src.app.services.operator_queries import query_operator_skill

logger = logging.getLogger(__name__)

def register_operator_skill_tool(mcp, app):
    @mcp.tool(description="获取干员技能数据（默认第1个技能，等级10）。不生成图片。")
    async def get_operator_skill(
        operator_name: Annotated[str, Field(description="干员名")],
        operator_name_prefix: Annotated[str, Field(description="干员名的前缀，没有则为空")] = "",
        index: Annotated[int, Field(description="技能序号，从1开始")] = 1,
        level: Annotated[int, Field(description="技能等级 1~10（8~10为专精一/二/三）")] = 10,
    ) -> dict:
        if not getattr(app.state, "ctx", None):
            return {"message": "未初始化数据上下文"}

        context: AppContext = app.state.ctx
        result = await query_operator_skill(
            context,
            operator_name=operator_name,
            operator_name_prefix=operator_name_prefix,
            index=index,
            level=level,
        )
        result_payload = result.to_response()
        logger.info(f"查询干员技能信息成功：{json.dumps(result_payload, ensure_ascii=False)}")
        return result_payload



