from __future__ import annotations

import logging

from src.app.services.integrated_strategy_collectible_assets import (
    attach_collectible_icon_artifacts,
)
from src.app.services.operator_queries import (
    QueryExecutionResult,
    resolve_search_items_by_ids,
    search,
)
from src.app.services.search_card import (
    SEARCH_SELECTION_CARD_MAX_ITEMS,
    SEARCH_SELECTION_CARD_TEMPLATE,
    build_search_selection_query_result,
)
from src.app.services.search_card_cache import (
    SearchCardCache,
    build_search_result_cache_key,
)
from src.helpers.card_urls import build_card_url


logger = logging.getLogger(__name__)


async def query_search(
    context,
    query: str,
    limit: int = 10,
) -> QueryExecutionResult:
    """执行统一搜索，并在多候选时附加有界缓存的分类选择卡。"""
    # AI-CORRECTION 2026-11-10: 搜索仅返回候选及可选图标；选择卡由
    # query_search_card 根据 agent 筛选后的 ID 独立组装，不再自动渲染。
    result = search(context, query=query, limit=limit)
    data = result.data
    if not isinstance(data, dict):
        return result
    items = data.get("items")
    if not isinstance(items, list):
        return result

    await _attach_search_icons(context, data)
    return result


async def query_search_card(context, ids: list[str]) -> QueryExecutionResult:
    """根据筛选后的 ID 组装选择卡，编号和缓存键均遵循传入顺序。"""
    if not isinstance(ids, list) or not 1 <= len(ids) <= SEARCH_SELECTION_CARD_MAX_ITEMS:
        return QueryExecutionResult(
            message=f"ids 必须包含 1~{SEARCH_SELECTION_CARD_MAX_ITEMS} 个搜索结果 ID"
        )
    if any(not isinstance(item_id, str) or not item_id.strip() for item_id in ids):
        return QueryExecutionResult(message="ids 中的每个 ID 必须是非空字符串")
    normalized_ids = [item_id.strip() for item_id in ids]
    if len(set(normalized_ids)) != len(normalized_ids):
        return QueryExecutionResult(message="ids 不能包含重复的搜索结果 ID")

    bundle = context.data_repository.get_bundle()
    try:
        items = resolve_search_items_by_ids(bundle, normalized_ids)
    except ValueError as exc:
        return QueryExecutionResult(message=str(exc))
    result = QueryExecutionResult(data={"items": items})
    collectible_artifacts = await _attach_search_icons(context, result.data)

    # AI-REMOVED 2026-11-10:
    # Reason: 独立组装工具允许展示单个选中结果。
    # Trigger: 搜索与选择卡生成解耦，agent 显式指定要展示的 ID。
    # Evidence: 原 query_search 在候选不足两项时提前返回。
    # Replacement: query_search_card 的 1~20 项参数校验。
    # Risk: Low；Human Review: Required
    # Original code:
    # if len(items) < 2:
    #     return result

    try:
        card_payload, fingerprint = build_search_selection_query_result(
            context,
            items,
            collectible_artifacts=collectible_artifacts,
        )
        cache_key = build_search_result_cache_key(items)
        cache = _get_search_card_cache(context)

        async def render_card():
            return await context.card_service.get(
                template=SEARCH_SELECTION_CARD_TEMPLATE,
                payload_key=cache_key,
                payload=card_payload,
                format="png",
            )

        artifact = await cache.get_or_render(
            cache_key=cache_key,
            fingerprint=fingerprint,
            render=render_card,
        )
        if artifact is None:
            result.message = "搜索卡片未生成，可能超出缓存大小限制；可使用 data.items 展示候选"
            return result

        if getattr(context, "prefer_local_artifact_path", False):
            result.image_path = str(artifact.path)
        try:
            result.image_url = build_card_url(
                cfg=context.cfg,
                template=SEARCH_SELECTION_CARD_TEMPLATE,
                payload_key=cache_key,
                format="png",
            )
        except RuntimeError:
            logger.info("未配置 BaseUrl，统一搜索卡片仅生成本地缓存")
    except Exception:
        logger.warning("生成统一搜索选择卡失败，仍返回结构化结果", exc_info=True)
        result.message = "生成搜索卡片失败，可使用 data.items 展示候选"

    return result


async def _attach_search_icons(context, data: dict) -> dict:
    try:
        return await attach_collectible_icon_artifacts(context, {"data": data})
    except Exception:
        logger.warning("准备统一搜索藏品图标失败，已保留无图结果", exc_info=True)
        return {}


def _get_search_card_cache(context) -> SearchCardCache:
    cache = getattr(context, "search_card_cache", None)
    if isinstance(cache, SearchCardCache):
        return cache
    cache = SearchCardCache(context.cfg)
    try:
        context.search_card_cache = cache
    except (AttributeError, TypeError):
        pass
    return cache
