from __future__ import annotations

import logging

from src.app.context import AppContext
from src.app.services.integrated_strategy_collectible_assets import (
    resolve_collectible_icon_artifact,
)
from src.app.services.integrated_strategy_collectible_output import (
    build_collectible_payload,
)
from src.app.services.operator_queries import QueryExecutionResult
from src.domain.services.operator import build_operator_template_font_url
from src.domain.types import QueryResult
from src.helpers.card_urls import build_card_url


logger = logging.getLogger(__name__)

COLLECTIBLE_CARD_REVISION = "collectible-v3"
COLLECTIBLE_CARD_TEMPLATE = "integrated_strategy_collectible"


async def query_integrated_strategy_collectible_by_id(
    context: AppContext,
    collectible_id: str,
) -> QueryExecutionResult:
    """按统一搜索返回的唯一 ID 查询一个藏品并生成详情卡片。"""
    normalized_id = str(collectible_id or "").strip()
    if not normalized_id:
        return QueryExecutionResult(message="collectible_id 不能为空")

    try:
        bundle = context.data_repository.get_bundle()
        collectible = (bundle.integrated_strategy_collectibles or {}).get(
            normalized_id
        )
        if not isinstance(collectible, dict):
            return QueryExecutionResult(
                message=f"未找到集成战略藏品ID: {normalized_id}"
            )

        structured_payload = build_collectible_payload(
            collectible,
            include_obtain_approach=True,
        )
        icon_artifact = None
        icon_id = str(collectible.get("icon_id") or "").strip()
        if icon_id:
            try:
                icon_artifact = await resolve_collectible_icon_artifact(
                    context,
                    icon_id,
                )
            except Exception:
                logger.warning(
                    "准备集成战略藏品图标失败，详情卡片将以无图模式生成: collectible_id=%s icon_id=%s",
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
            type="integrated_strategy_collectible",
            key=normalized_id,
            title=str(structured_payload.get("name") or normalized_id),
            data={
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
            f"collectible:{normalized_id}:{bundle_version}:"
            f"{COLLECTIBLE_CARD_REVISION}:{icon_revision}"
        )

        data_url = None
        try:
            await context.card_service.get(
                template=COLLECTIBLE_CARD_TEMPLATE,
                payload_key=payload_key,
                payload=card_payload,
                format="json",
            )
            try:
                data_url = build_card_url(
                    cfg=context.cfg,
                    template=COLLECTIBLE_CARD_TEMPLATE,
                    payload_key=payload_key,
                    format="json",
                )
            except RuntimeError:
                logger.info(
                    "未配置 BaseUrl，藏品 JSON 仅生成本地缓存: collectible_id=%s",
                    normalized_id,
                )
        except Exception:
            logger.warning(
                "准备集成战略藏品 JSON 产物失败: collectible_id=%s",
                normalized_id,
                exc_info=True,
            )

        image_url = None
        image_path = None
        try:
            artifact = await context.card_service.get(
                template=COLLECTIBLE_CARD_TEMPLATE,
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
                    template=COLLECTIBLE_CARD_TEMPLATE,
                    payload_key=payload_key,
                    format="png",
                )
            except RuntimeError:
                logger.info(
                    "未配置 BaseUrl，藏品卡片仅生成本地缓存: collectible_id=%s",
                    normalized_id,
                )
        except Exception:
            logger.warning(
                "准备集成战略藏品详情卡片失败，仍返回结构化数据: collectible_id=%s",
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
            "按 ID 查询集成战略藏品失败: collectible_id=%s",
            collectible_id,
        )
        return QueryExecutionResult(message="查询集成战略藏品时发生错误.")
