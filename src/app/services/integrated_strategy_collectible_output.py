from __future__ import annotations

from collections.abc import Mapping
from typing import Any


COLLECTIBLE_RARITY_NAMES = {
    "NORMAL": "普通",
    "RARE": "稀有",
    "SUPER_RARE": "超稀有",
}


def build_collectible_payload(
    collectible: Mapping[str, Any],
    *,
    include_obtain_approach: bool = False,
) -> dict[str, object]:
    """把解包藏品记录转换为统一搜索和详情工具共用的输出结构。"""
    rarity = str(collectible.get("rarity") or "").strip()
    payload: dict[str, object] = {
        "id": str(collectible.get("id") or "").strip(),
        "name": str(collectible.get("name") or "").strip(),
        "type": "集成战略藏品",
        "topic_id": str(collectible.get("topic_id") or "").strip(),
        "topic_name": str(collectible.get("topic_name") or "").strip(),
        "icon_id": str(collectible.get("icon_id") or "").strip(),
        "description": str(collectible.get("description") or "").strip(),
        "usage": str(collectible.get("usage") or "").strip(),
        "rarity": COLLECTIBLE_RARITY_NAMES.get(rarity, rarity),
        "unlock_condition": str(
            collectible.get("unlock_condition") or ""
        ).strip(),
        "can_exchange": bool(collectible.get("can_sacrifice")),
    }
    if include_obtain_approach:
        payload["obtain_approach"] = str(
            collectible.get("obtain_approach") or ""
        ).strip()
    return payload
