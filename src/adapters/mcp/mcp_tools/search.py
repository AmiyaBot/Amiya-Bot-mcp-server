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
from src.app.services.search_queries import query_search

logger = logging.getLogger(__name__)

_SEARCH_TOOL_DESC = """本工具是资源统一搜索入口，任何查询都应先调用本工具。
支持按名称、代号或定期同步的常用别名模糊搜索「干员」「干员的召唤物」「干员皮肤」「材料」「关卡」「敌人」与「集成战略藏品」，返回候选的 id、name、type；别名命中的干员、材料或敌人仍返回其真实类型，并附带 from_alias；召唤物、皮肤、关卡、敌人和集成战略藏品条目会附带用于区分候选的字段。
存在多个候选时还会返回 card_image_url 分类选择卡；卡片序号与 items 原始顺序一致，应优先展示该卡并让用户回复序号或名称。单个明确候选不生成搜索选择卡。
- 干员：用返回的 id 调用 get_operator_basic_data（推荐，返回结构化数据 + card_image_url 卡片图片）；需要完整技能列表及所有技能等级数据时调用 get_operator_skill；培养材料和模组分别调用 get_operator_material / get_operator_modules；
- 召唤物：用返回的 id 调用 get_token_detail 查看召唤物详情；也可以用 operator_id 查看所属干员。
- 皮肤：用返回的 operator_id 调用 get_operator_skins 查看所属干员的皮肤。
- 材料：用返回的 id 调用 get_material 查看材料详情、合成路线、官方关卡掉落和材料卡片。
- 关卡：用返回的 id 调用 get_stage_data 查看关卡规则、敌人、掉落和关卡卡片。
- 敌人：用返回的 id 调用 get_enemy_data 查看敌人能力、等级属性、关联单位和敌人卡片。
- 集成战略藏品：不同主题中的同名藏品会分别返回。根据所属主题和效果选择唯一候选后，用该候选的 id 调用 get_integrated_strategy_collectible_detail 获取详情卡片；不要把名称传给详情工具。搜索结果也会直接附带描述、效果、稀有度、解锁条件、是否可交换及按需缓存的 icon_url。

提示：服务会每小时同步一次官方旧版全局别名表；若某个新外号尚未收录，再联网确认其正式名称。
"""


def register_search_tool(mcp, app):
    @mcp.tool(description=_SEARCH_TOOL_DESC)
    async def search(
        query: Annotated[str, Field(description="搜索关键词（干员、召唤物、皮肤、材料、关卡、敌人或集成战略藏品名称/代号/常用别名），支持模糊搜索")],
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

            result = await query_search(
                context,
                query=query,
            )
            result_payload = result.to_response()
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
