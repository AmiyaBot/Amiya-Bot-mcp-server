from __future__ import annotations

import base64
from collections import OrderedDict
from collections.abc import Mapping
import hashlib
from pathlib import Path
from typing import Any

from src.app.services.integrated_strategy_collectible_assets import (
    IntegratedStrategyCollectibleIconArtifact,
)
from src.app.services.search_card_cache import build_search_card_fingerprint
from src.app.services.stage_queries import resolve_stage_map_paths
from src.domain.services.operator import build_operator_template_font_url
from src.domain.types import QueryResult


SEARCH_SELECTION_CARD_REVISION = "search-selection-v1"
SEARCH_SELECTION_CARD_TEMPLATE = "search_selection"
SEARCH_SELECTION_CARD_MAX_ITEMS = 20

_GROUP_CONFIG = {
    "干员": {"layout": "portrait", "css_class": "operator"},
    "皮肤": {"layout": "portrait", "css_class": "skin"},
    "召唤物": {"layout": "square", "css_class": "token"},
    "敌人": {"layout": "square", "css_class": "enemy"},
    "关卡": {"layout": "stage", "css_class": "stage"},
    "材料": {"layout": "square", "css_class": "material"},
    "集成战略藏品": {
        "layout": "square",
        "css_class": "collectible",
    },
}


def build_search_selection_query_result(
    context,
    items: list[dict[str, object]],
    *,
    collectible_artifacts: Mapping[
        str, IntegratedStrategyCollectibleIconArtifact
    ]
    | None = None,
) -> tuple[QueryResult, str]:
    """把统一搜索候选转换为分类选择卡数据，并返回内容指纹。"""
    bundle = context.data_repository.get_bundle()
    artifacts = collectible_artifacts or {}
    displayed_items = items[:SEARCH_SELECTION_CARD_MAX_ITEMS]
    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for index, item in enumerate(displayed_items, start=1):
        item_type = str(item.get("type") or "").strip()
        config = _GROUP_CONFIG.get(
            item_type,
            {"layout": "square", "css_class": "unknown"},
        )
        group = grouped.setdefault(
            item_type or "其他",
            {
                "type": item_type or "其他",
                "layout": config["layout"],
                "css_class": config["css_class"],
                "items": [],
            },
        )
        group["items"].append(
            _build_display_item(
                context,
                bundle,
                item,
                index=index,
                collectible_artifact=artifacts.get(
                    str(item.get("id") or "")
                ),
            )
        )

    groups = list(grouped.values())
    for group in groups:
        group["count"] = len(group["items"])

    bundle_version = str(getattr(bundle, "version", None) or "v0")
    fingerprint_payload = {
        "revision": SEARCH_SELECTION_CARD_REVISION,
        "bundle_version": bundle_version,
        "total": len(items),
        "displayed": len(displayed_items),
        "ordered_ids": [str(item.get("id") or "") for item in items],
        "groups": [_fingerprint_group(group) for group in groups],
    }
    fingerprint = build_search_card_fingerprint(fingerprint_payload)
    result = QueryResult(
        type=SEARCH_SELECTION_CARD_TEMPLATE,
        key=fingerprint,
        title="搜索结果",
        data={
            "groups": groups,
            "total": len(items),
            "displayed": len(displayed_items),
            "remaining": max(0, len(items) - len(displayed_items)),
            "template_font_url": build_operator_template_font_url(
                context.cfg.ProjectRoot
            ),
        },
    )
    return result, fingerprint


def _build_display_item(
    context,
    bundle,
    item: Mapping[str, object],
    *,
    index: int,
    collectible_artifact: IntegratedStrategyCollectibleIconArtifact | None,
) -> dict[str, Any]:
    item_id = str(item.get("id") or "").strip()
    item_type = str(item.get("type") or "").strip()
    name = str(item.get("name") or item_id).strip()
    image_path: Path | None = None
    subtitle = ""
    meta = ""

    if item_type == "干员":
        image_path = _operator_portrait_path(context.cfg.ResourcePath, item_id)
        operator = (getattr(bundle, "operators", {}) or {}).get(item_id)
        if operator is not None:
            subtitle = str(getattr(operator, "classes", "") or "").strip()
            rarity = int(getattr(operator, "rarity", 0) or 0)
            meta = f"{rarity}★" if rarity else ""
    elif item_type == "皮肤":
        image_path = (
            Path(context.cfg.ResourcePath)
            / "assets"
            / "portrait"
            / f"{item_id}.png"
        )
        subtitle = str(item.get("operator_name") or "").strip()
    elif item_type == "召唤物":
        image_path = (
            Path(context.cfg.ResourcePath)
            / "assets"
            / "avatar"
            / f"{item_id}#1.png"
        )
        subtitle = str(item.get("operator_name") or "").strip()
    elif item_type == "敌人":
        image_path = (
            Path(context.cfg.ResourcePath)
            / "assets"
            / "enemy"
            / f"{item_id}.png"
        )
        subtitle = str(item.get("enemy_index") or "").strip()
        meta = str(item.get("enemy_level") or "").strip()
    elif item_type == "关卡":
        map_paths = resolve_stage_map_paths(context.cfg.ResourcePath, item_id)
        image_path = map_paths[0] if map_paths else None
        subtitle = str(item.get("code") or "").strip()
        difficulty = str(item.get("difficulty") or "").strip()
        stage_type = str(item.get("stage_type") or "").strip()
        meta = " · ".join(value for value in (stage_type, difficulty) if value)
        if len(map_paths) > 1:
            meta = " · ".join(
                value for value in (meta, f"{len(map_paths)}张地图") if value
            )
    elif item_type == "材料":
        material = (getattr(bundle, "materials", {}) or {}).get(item_id) or {}
        icon_id = str(material.get("icon_id") or "").strip()
        if icon_id:
            image_path = (
                Path(context.cfg.ResourcePath) / "assets" / "item" / icon_id
            )
            if not image_path.suffix:
                image_path = image_path.with_suffix(".png")
        rarity = material.get("rarity")
        meta = f"稀有度 {rarity}" if rarity not in (None, "") else ""
    elif item_type == "集成战略藏品":
        subtitle = str(item.get("topic_name") or "").strip()
        meta = str(item.get("rarity") or "").strip()

    if collectible_artifact is not None:
        image_data = collectible_artifact.to_data_uri()
        image_signature = _path_signature(
            collectible_artifact.path,
            context.cfg.ResourcePath,
        )
    else:
        image_data = _image_data_uri(image_path)
        image_signature = _path_signature(image_path, context.cfg.ResourcePath)

    return {
        "index": index,
        "id": item_id,
        "name": name,
        "type": item_type,
        "image_data": image_data or "",
        "image_signature": image_signature,
        "subtitle": subtitle,
        "meta": meta,
    }


def _operator_portrait_path(resource_root: Path, operator_id: str) -> Path | None:
    portrait_root = Path(resource_root) / "assets" / "portrait"
    base = portrait_root / f"{operator_id}#1.png"
    if base.is_file():
        return base
    candidates = sorted(portrait_root.glob(f"{operator_id}#*.png"))
    return candidates[0] if candidates else None


def _image_data_uri(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        if path.is_symlink() or not path.is_file():
            return None
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except OSError:
        return None


def _path_signature(path: Path | None, resource_root: Path) -> str:
    if path is None:
        return "missing"
    try:
        if path.is_symlink() or not path.is_file():
            return "missing"
        stat = path.stat()
        try:
            label = str(path.relative_to(resource_root)).replace("\\", "/")
        except ValueError:
            label = path.name
        value = f"{label}:{stat.st_size}:{stat.st_mtime_ns}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
    except OSError:
        return "missing"


def _fingerprint_group(group: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": group.get("type"),
        "layout": group.get("layout"),
        "css_class": group.get("css_class"),
        "items": [
            {
                key: value
                for key, value in item.items()
                if key != "image_data"
            }
            for item in group.get("items", [])
        ],
    }
