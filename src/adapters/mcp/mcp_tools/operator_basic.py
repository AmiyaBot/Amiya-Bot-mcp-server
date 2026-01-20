import json
import logging
from typing import Annotated

from pydantic import Field

from src.domain.models.operator import Operator
from src.domain.services.operator import search_operator_by_name
from src.helpers.card_urls import build_card_url
from src.helpers.gamedata.search import build_sources, search_source_spec
from src.app.context import AppContext
from src.domain.services.operator_basic import get_operator_basic_core, OperatorNotFoundError
from src.app.renderers.types import Renderer

logger = logging.getLogger(__name__)

tool_description = """获取干员的基础信息和属性。同时还附加一张包含干员信息和立绘的图片。
如果可以，请使用中文名称进行查询。

Args:
    operator_name (str): 干员名
    operator_name_prefix (str): 干员名的前缀，没有则为空，如干员假日威龙陈的前缀为“假日威龙”

Returns:
    str: 一个Json对象，文本可读的干员信息包含在data字段中，图片的URL包含在image_url字段中。
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
            return "未初始化数据上下文"

        context: AppContext = app.state.ctx

        try:
            operator_combine = operator_name_prefix + operator_name

            search_sources = build_sources(context.data_repository.get_bundle(), source_key=["name"])
            search_results = search_source_spec([operator_combine,operator_name], sources=search_sources)

            # 注意：你原本的判断是 len(search_results.matches) > 1
            # 更稳：只看 name key 的命中
            if not search_results:
                return {
                    "message": f"未找到干员: {operator_name_prefix} {operator_name}"
                }

            name_matches = search_results.by_key("name")
            if len(name_matches) != 1:

                # matched_names = [m.matched_text for m in search_results.matches if m.key == "name"]
                # return {
                #     "message": f"找到多个匹配的干员名称，需要用户做出选择",
                #     "candidates": matched_names
                # }

                # 改为先判断两个exact match是否存在，优先operator_combine，如果存在，则直接用它
                exact_matches = [m for m in name_matches if m.matched_text == operator_combine]
                if not exact_matches:
                    exact_matches = [m for m in name_matches if m.matched_text == operator_name]
                if len(exact_matches) == 1:
                    name_matches = exact_matches
                else:
                    matched_names = [m.matched_text for m in name_matches]
                    matched_names = list(dict.fromkeys(matched_names))
                    return {
                        "message": "找到多个匹配的干员名称，需要用户做出选择",
                        "candidates": matched_names
                    }

            # 优先json_renderer,然后text_renderer,然后直接json format
            op: Operator = name_matches[0].value

            # TODO 领域查询，需要进行替换，目前该函数的目的是为了配合旧版模板
            result = search_operator_by_name(context, op.name)

            # 生成 payload_key：要求包含 version
            bundle = context.data_repository.get_bundle()
            bundle_version = getattr(bundle, "version", None) or getattr(bundle, "hash", None) or "v0"

            payload_key = f"operator:{op.name}:{bundle_version}"

            # ✅ 交给 CardService：如果磁盘已有 png，就直接命中返回；否则现场渲染
            text_artifact = await context.card_service.get(
                template="operator_info",
                payload_key=payload_key,
                payload=result,
                format="txt",
                params=None,
            )

            img_artifact = await context.card_service.get(
                template="operator_info",
                payload_key=payload_key,
                payload=result,
                format="png",
                params=None,
            )

            image_url = build_card_url(
                cfg=context.cfg,
                template="operator_info",
                payload_key=payload_key,
                format="png",
            )

            result = {
                "data": text_artifact.read_text(),
                "image_url": image_url,
            }
        except Exception:
            logger.exception("查询失败")
            return {
                "message": "查询干员信息时发生错误."
            }


        logger.info(f"查询干员基础信息成功：{json.dumps(result, ensure_ascii=False)}")
        return result
