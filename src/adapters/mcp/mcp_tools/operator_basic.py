import json
import logging
from typing import Annotated

from pydantic import Field

from src.app.context import AppContext
from src.app.services.operator_queries import query_operator_basic

logger = logging.getLogger(__name__)

tool_description = """获取干员的基础信息和属性。同时还附加一张干员立绘图片。
如果可以，请使用中文名称进行查询。

Args:
    operator_name (str): 干员名
    operator_name_prefix (str): 干员名的前缀，没有则为空，如干员假日威龙陈的前缀为“假日威龙”

Returns:
    str: 一个Json对象，语义化的结构化干员信息包含在data字段中，图片的URL包含在image_url字段中。
    请尽可能向用户展示这张图片，无论用户是否明确需要图片资料。
"""


def register_operator_basic_tool(mcp, app):
    @mcp.tool(description=tool_description)
    async def get_operator_basic(
        operator_name: Annotated[str, Field(description='干员名')],
        operator_name_prefix: Annotated[str, Field(description='干员名的前缀，没有则为空')] = '',
    ) -> dict:

        logger.info(f"查询干员基础信息：{operator_name_prefix}{operator_name}")

        if not getattr(app.state, "ctx", None):
            return {"message": "未初始化数据上下文"}

        context: AppContext = app.state.ctx
        result = await query_operator_basic(
            context,
            operator_name=operator_name,
            operator_name_prefix=operator_name_prefix,
        )
        result_payload = result.to_response()
        logger.info(f"查询干员基础信息成功：{json.dumps(result_payload, ensure_ascii=False)}")
        return result_payload
