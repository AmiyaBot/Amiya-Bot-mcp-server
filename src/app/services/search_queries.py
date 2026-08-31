from __future__ import annotations

import logging

from src.app.services.integrated_strategy_collectible_assets import (
    attach_collectible_icon_artifacts,
)
from src.app.services.operator_queries import QueryExecutionResult, search
from src.app.services.search_card import (
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
    result = search(context, query=query, limit=limit)
    data = result.data
    if not isinstance(data, dict):
        return result
    items = data.get("items")
    if not isinstance(items, list):
        return result

    collectible_artifacts = {}
    try:
        collectible_artifacts = await attach_collectible_icon_artifacts(
            context,
            {"data": data},
        )
    except Exception:
        logger.warning("准备统一搜索藏品图标失败，已保留无图结果", exc_info=True)

    if len(items) < 2:
        return result

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

    return result


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
