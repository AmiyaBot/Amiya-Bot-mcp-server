from __future__ import annotations

import logging

from src.app.context import AppContext
from src.app.services.integrated_strategy_collectible_assets import (
    resolve_collectible_icon_artifact,
)
from src.app.services.integrated_strategy_item_output import (
    build_integrated_strategy_item_payload,
)
from src.app.services.operator_queries import QueryExecutionResult
from src.domain.services.operator import build_operator_template_font_url
from src.domain.types import QueryResult
from src.helpers.card_urls import build_card_url


logger = logging.getLogger(__name__)

ITEM_CARD_REVISION = "strategy-item-v2"
ITEM_CARD_TEMPLATE = "integrated_strategy_collectible"


async def query_integrated_strategy_item_by_id(
    context: AppContext,
    item_id: str,
) -> QueryExecutionResult:
    """按统一搜索返回的代表 ID 查询藏品或主题机制道具。"""
    normalized_id = str(item_id or "").strip()
    if not normalized_id:
        return QueryExecutionResult(message="item_id 不能为空")

    try:
        bundle = context.data_repository.get_bundle()
        item = (getattr(bundle, "integrated_strategy_items", {}) or {}).get(
            normalized_id
        )
        if not isinstance(item, dict):
            return QueryExecutionResult(
                message=f"未找到集成战略物品ID: {normalized_id}"
            )

        structured_payload = build_integrated_strategy_item_payload(
            item,
            include_obtain_approach=True,
        )
        icon_artifact = None
        icon_id = str(item.get("icon_id") or "").strip()
        if icon_id:
            try:
                icon_artifact = await resolve_collectible_icon_artifact(
                    context,
                    icon_id,
                )
            except Exception:
                logger.warning(
                    "准备集成战略物品图标失败，详情卡片将以无图模式生成: item_id=%s icon_id=%s",
                    normalized_id,
                    icon_id,
                    exc_info=True,
                )

        if icon_artifact is not None:
            if icon_artifact.url:
                structured_payload["icon_url"] = icon_artifact.url
            if context.prefer_local_artifact_path:
                structured_payload["icon_path"] = str(icon_artifact.path)

        card_payload = QueryResult(
            type="integrated_strategy_item",
            key=normalized_id,
            title=str(structured_payload.get("name") or normalized_id),
            data={
                # 复用原藏品卡模板的数据槽；模板展示名称已泛化。
                "collectible": structured_payload,
                "icon_data": (
                    icon_artifact.to_data_uri()
                    if icon_artifact is not None
                    else None
                ),
                "template_font_url": build_operator_template_font_url(
                    context.cfg.ProjectRoot
                ),
            },
        )
        bundle_version = getattr(bundle, "version", None) or "v0"
        icon_revision = "with-icon" if icon_artifact is not None else "no-icon"
        payload_key = (
            f"strategy-item:{normalized_id}:{bundle_version}:"
            f"{ITEM_CARD_REVISION}:{icon_revision}"
        )

        data_url = None
        try:
            await context.card_service.get(
                template=ITEM_CARD_TEMPLATE,
                payload_key=payload_key,
                payload=card_payload,
                format="json",
            )
            try:
                data_url = build_card_url(
                    cfg=context.cfg,
                    template=ITEM_CARD_TEMPLATE,
                    payload_key=payload_key,
                    format="json",
                )
            except RuntimeError:
                logger.info(
                    "未配置 BaseUrl，集成战略物品 JSON 仅生成本地缓存: item_id=%s",
                    normalized_id,
                )
        except Exception:
            logger.warning(
                "准备集成战略物品 JSON 产物失败: item_id=%s",
                normalized_id,
                exc_info=True,
            )

        image_url = None
        image_path = None
        try:
            artifact = await context.card_service.get(
                template=ITEM_CARD_TEMPLATE,
                payload_key=payload_key,
                payload=card_payload,
                format="png",
                params={
                    "viewport": {
                        "width": 1000,
                        "height": 700,
                        "deviceScaleFactor": 1,
                    },
                    "full_page": True,
                    "wait_until": "load",
                },
            )
            if context.prefer_local_artifact_path:
                image_path = str(artifact.path)
            try:
                image_url = build_card_url(
                    cfg=context.cfg,
                    template=ITEM_CARD_TEMPLATE,
                    payload_key=payload_key,
                    format="png",
                )
            except RuntimeError:
                logger.info(
                    "未配置 BaseUrl，集成战略物品卡片仅生成本地缓存: item_id=%s",
                    normalized_id,
                )
        except Exception:
            logger.warning(
                "准备集成战略物品详情卡片失败，仍返回结构化数据: item_id=%s",
                normalized_id,
                exc_info=True,
            )

        return QueryExecutionResult(
            data=structured_payload,
            image_url=image_url,
            data_url=data_url,
            image_path=image_path,
        )
    except Exception:
        logger.exception(
            "按 ID 查询集成战略物品失败: item_id=%s",
            item_id,
        )
        return QueryExecutionResult(message="查询集成战略物品时发生错误.")
