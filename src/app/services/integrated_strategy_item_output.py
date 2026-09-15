from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.app.services.integrated_strategy_collectible_output import (
    COLLECTIBLE_RARITY_NAMES,
)


INTEGRATED_STRATEGY_ITEM_TYPES = frozenset(
    {
        "集成战略藏品",
        "剧目",
        "骰子",
        "密文板",
        "构想",
        "通宝",
        "零件",
    }
)


def build_integrated_strategy_item_payload(
    item: Mapping[str, Any],
    *,
    include_obtain_approach: bool = False,
) -> dict[str, object]:
    """转换可查询的主题机制道具，并保留聚合后的变体说明。"""
    rarity = str(item.get("rarity") or "").strip()
    if rarity == "NONE":
        rarity = ""
    payload: dict[str, object] = {
        "id": str(item.get("id") or "").strip(),
        "name": str(item.get("name") or "").strip(),
        "type": str(item.get("display_type") or "集成战略物品").strip(),
        "game_type": str(item.get("game_type") or "").strip(),
        "topic_id": str(item.get("topic_id") or "").strip(),
        "topic_name": str(item.get("topic_name") or "").strip(),
        "icon_id": str(item.get("icon_id") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "usage": str(item.get("usage") or "").strip(),
        "rarity": COLLECTIBLE_RARITY_NAMES.get(rarity, rarity),
        "sub_type": str(item.get("sub_type_name") or "").strip(),
        "can_exchange": bool(item.get("can_sacrifice")),
    }
    variants = item.get("variants")
    if isinstance(variants, list) and len(variants) > 1:
        payload["variant_count"] = len(variants)
        payload["variants"] = [
            {
                "id": str(variant.get("id") or "").strip(),
                "name": str(variant.get("name") or "").strip(),
                "variant_name": str(
                    variant.get("variant_name") or ""
                ).strip(),
                "usage": str(variant.get("usage") or "").strip(),
                "variant_effect": str(
                    variant.get("variant_effect") or ""
                ).strip(),
                "icon_id": str(variant.get("icon_id") or "").strip(),
            }
            for variant in variants
            if isinstance(variant, Mapping)
        ]
    if include_obtain_approach:
        payload["obtain_approach"] = str(
            item.get("obtain_approach") or ""
        ).strip()
        payload["unlock_condition"] = str(
            item.get("unlock_condition") or ""
        ).strip()
    return payload
