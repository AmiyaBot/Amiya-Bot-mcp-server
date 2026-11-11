# 原文件 operator_search.py、原工具名 search_operator（2026-08-13 起重命名为 search.py / search）：
# 升级为资源统一搜索（干员、召唤物、皮肤、材料、关卡、敌人、集成战略藏品），作为任何查询的统一入口。
# AI-CORRECTION 2026-09-15: 搜索范围现已继续扩展至剧目、骰子、密文板、构想、通宝和零件。
# AI-CORRECTION 2026-08-24: 搜索范围现已包含干员皮肤和敌人；干员候选也可用于模组查询。
import logging
from typing import Annotated

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.search_card import SEARCH_SELECTION_CARD_MAX_ITEMS
from src.app.services.search_queries import query_search, query_search_card

logger = logging.getLogger(__name__)

_SEARCH_TOOL_DESC = """本工具是资源统一搜索入口，任何查询都应先调用本工具。
支持按名称、代号或定期同步的常用别名模糊搜索「干员」「干员的召唤物」「干员皮肤」「材料」「关卡」「敌人」、集成战略藏品及主题机制道具（剧目、骰子、密文板、构想、通宝、零件），返回候选的 id、name、type；别名命中的干员、材料或敌人仍返回其真实类型，并附带 from_alias；其他条目会附带用于区分候选的字段。
搜索只返回候选数据，不生成搜索卡。收到结果后必须结合用户当前问题和对话上下文筛选候选，排除明显无关的模糊匹配；无法确定的相关候选应保留给用户选择。
需要向用户展示搜索结果或让用户选择时，应调用 build_search_card(ids=[筛选后的候选ID...])，并展示返回的 card_image_url 图片，让用户回复序号或名称；不要直接把全部模糊命中展示给用户。卡片序号从 1 开始，对应组装工具返回的 data.items 顺序，不再对应原搜索列表。上下文已能确定唯一目标时可直接调用相应详情工具；筛选后无相关候选时，应说明未找到相关结果或调整关键词继续搜索。
- 干员：用返回的 id 调用 get_operator_basic_data（推荐，返回结构化数据 + card_image_url 卡片图片）；需要完整技能列表及所有技能等级数据时调用 get_operator_skill；培养材料和模组分别调用 get_operator_material / get_operator_modules；
- 召唤物：用返回的 id 调用 get_token_detail 查看召唤物详情；也可以用 operator_id 查看所属干员。
- 皮肤：用返回的 operator_id 调用 get_operator_skins 查看所属干员的皮肤。
- 材料：用返回的 id 调用 get_material 查看材料详情、合成路线、官方关卡掉落和材料卡片。
- 关卡：用返回的 id 调用 get_stage_data 查看关卡规则、敌人、掉落和关卡卡片。
- 敌人：用返回的 id 调用 get_enemy_data 查看敌人能力、等级属性、关联单位和敌人卡片。
- 集成战略物品：不同主题或不同效果的同名物品会分别返回；剧目的普通/猩红版本、骰子的使用场景及通宝品相会合并在 variants。通宝通过 sub_type 区分花钱/衡钱/厉钱，黑流树海零件通过 sub_type 区分加工品/自然物/概念体。用候选 id 调用 get_integrated_strategy_item_detail 获取详情卡片；不要把名称传给详情工具。搜索结果也会直接附带描述、效果、稀有度、子类型、变体及按需缓存的 icon_url。

提示：服务会每小时同步一次官方旧版全局别名表；若某个新外号尚未收录，再联网确认其正式名称。
"""


_BUILD_SEARCH_CARD_TOOL_DESC = """将 search 搜索结果中经上下文筛选的候选组装为一张分类搜索卡。
先根据用户意图筛除明显无关项，再传入选中条目的真实 id；可合并多次搜索的候选，不传名称、序号或自行编造的 ID。
ids 必须包含 1~20 个不重复 ID，传入顺序决定卡片序号（从 1 开始）；返回 data.items 与该顺序一致，供用户回复序号后定位对应详情工具。
应向用户展示 card_image_url 指向的图片；卡片生成失败时才使用 data.items 展示文字候选。无效 ID 会返回错误，不会静默忽略或重新模糊搜索。
"""


def register_search_tool(mcp, app):
    @mcp.tool(description=_SEARCH_TOOL_DESC)
    async def search(
        query: Annotated[str, Field(description="搜索关键词（干员、召唤物、皮肤、材料、关卡、敌人、集成战略藏品或机制道具名称/代号/常用别名），支持模糊搜索")],
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
                    "search 调用上下文: repo_ready=%s bundle_operators=%s name_index=%s token_name_index=%s enemy_alias_index=%s strategy_item_alias_index=%s",
                    repo.is_ready(),
                    len(bundle.operators) if bundle and bundle.operators else 0,
                    len(bundle.operator_name_to_id) if bundle and bundle.operator_name_to_id else 0,
                    len(bundle.token_name_to_id) if bundle and bundle.token_name_to_id else 0,
                    len(bundle.enemy_alias_to_ids) if bundle and bundle.enemy_alias_to_ids else 0,
                    len(
                        getattr(
                            bundle,
                            "integrated_strategy_item_alias_to_ids",
                            {},
                        )
                    )
                    if bundle
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

    @mcp.tool(description=_BUILD_SEARCH_CARD_TOOL_DESC)
    async def build_search_card(
        ids: Annotated[
            list[str],
            Field(
                description="根据对话上下文从 search 候选中筛选的 ID 列表，按期望的卡片编号顺序传入，不可重复",
                min_length=1,
                max_length=SEARCH_SELECTION_CARD_MAX_ITEMS,
            ),
        ],
    ) -> dict:
        tool_name = "build_search_card"
        started_at = log_tool_start(logger, tool_name, ids=ids)
        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                result_payload = {"message": "未初始化数据上下文"}
            else:
                result = await query_search_card(app.state.ctx, ids=ids)
                result_payload = result.to_response()
            log_tool_end(logger, tool_name, started_at, result_payload)
            return result_payload
        except Exception:
            log_tool_exception(logger, tool_name, started_at, ids=ids)
            raise


# AI-REMOVED 2026-11-10:
# Reason: 用户仅授权结构化数据，撤回未经授权的卫戍协议查询和卡片接入。
# Trigger: 用户要求先去掉本次新增接口，后续按指导梳理添加。
# Evidence: 本次工作区 diff 中新增的卫戍协议工具、搜索和卡片代码。
# Replacement: None；仅保留 src/data/repository/bundle/autochess.py 数据结构化。
# Risk: Low；既有查询入口保持原行为。
# Human Review: Required
# Original code:
# # AI-CORRECTION 2026-11-10: 搜索范围增加卫戍协议盟约、棋子及策略，包含档期与教程标识。
# 支持卫戍协议盟约、棋子、策略名称（也支持“卫戍协议真理”这种限定名称）；候选带 activity_id、activity_name、version_id、ruleset/ruleset_name，用 id 调用 get_autochess_detail。不同档期和教程的同名条目不可混用。
