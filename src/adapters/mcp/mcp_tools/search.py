# 原文件 operator_search.py、原工具名 search_operator（2026-08-13 起重命名为 search.py / search）：
# 升级为资源统一搜索（干员、召唤物、皮肤、材料、关卡、敌人、集成战略藏品），作为任何查询的统一入口。
# AI-CORRECTION 2026-08-24: 搜索范围现已包含干员皮肤和敌人；干员候选也可用于模组查询。
import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.integrated_strategy_collectible_assets import (
    attach_collectible_icon_artifacts,
)
from src.app.services.operator_queries import search as search_query

logger = logging.getLogger(__name__)

_SEARCH_TOOL_DESC = """本工具是资源统一搜索入口，任何查询都应先调用本工具。
支持按名称或代号模糊搜索「干员」「干员的召唤物」「干员皮肤」「材料」「关卡」「敌人」与「集成战略藏品」，返回候选的 id、name、type；召唤物、皮肤、关卡、敌人和集成战略藏品条目会附带用于区分候选的字段。
- 干员：用返回的 id 调用 get_operator_basic_data（推荐，返回结构化数据 + card_image_url 卡片图片）；需要完整技能列表及所有技能等级数据时调用 get_operator_skill；培养材料和模组分别调用 get_operator_material / get_operator_modules；
- 召唤物：用返回的 id 调用 get_token_detail 查看召唤物详情；也可以用 operator_id 查看所属干员。
- 皮肤：用返回的 operator_id 调用 get_operator_skins 查看所属干员的皮肤。
- 材料：用返回的 id 调用 get_material 查看材料详情、合成路线、官方关卡掉落和材料卡片。
- 关卡：用返回的 id 调用 get_stage_data 查看关卡规则、敌人、掉落和关卡卡片。
- 敌人：用返回的 id 调用 get_enemy_data 查看敌人能力、等级属性、关联单位和敌人卡片。
- 集成战略藏品：不同主题中的同名藏品会分别返回。根据所属主题和效果选择唯一候选后，用该候选的 id 调用 get_integrated_strategy_collectible_detail 获取详情卡片；不要把名称传给详情工具。搜索结果也会直接附带描述、效果、稀有度、解锁条件及按需缓存的 icon_url。

提示：若搜不到结果，可能是用户使用了干员外号（非正式称呼）。此时可先联网搜索该外号对应的干员正式名称，再用正式名称重新调用本工具。
"""


def register_search_tool(mcp, app):
    @mcp.tool(description=_SEARCH_TOOL_DESC)
    async def search(
        query: Annotated[str, Field(description="搜索关键词（干员、召唤物、皮肤、材料、关卡、敌人或集成战略藏品名称/代号），支持模糊搜索")],
    ) -> dict:
        tool_name = "search"
        started_at = log_tool_start(
            logger,
            tool_name,
            query=query,
        )

        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, result_payload)
                return result_payload

            context: AppContext = app.state.ctx
            # 记录数据仓库就绪状态
            repo = getattr(context, "data_repository", None)
            if repo is not None:
                try:
                    bundle = repo.get_bundle()
                except Exception:
                    bundle = None
                logger.debug(
                    "search 调用上下文: repo_ready=%s bundle_operators=%s name_index=%s token_name_index=%s enemy_alias_index=%s collectible_alias_index=%s",
                    repo.is_ready(),
                    len(bundle.operators) if bundle and bundle.operators else 0,
                    len(bundle.operator_name_to_id) if bundle and bundle.operator_name_to_id else 0,
                    len(bundle.token_name_to_id) if bundle and bundle.token_name_to_id else 0,
                    len(bundle.enemy_alias_to_ids) if bundle and bundle.enemy_alias_to_ids else 0,
                    len(bundle.integrated_strategy_collectible_alias_to_ids)
                    if bundle and bundle.integrated_strategy_collectible_alias_to_ids
                    else 0,
                )
            else:
                logger.warning("search: data_repository 为 None")

            result = search_query(
                context,
                query=query,
            )
            result_payload = result.to_response()
            await attach_collectible_icon_artifacts(context, result_payload)
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(
                logger,
                tool_name,
                started_at,
                query=query,
            )
            raise
