from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any

from src.app.context import AppContext
from src.app.services.operator_queries import QueryExecutionResult
from src.domain.models.stage import Stage
from src.domain.services.operator import (
    build_operator_template_bg_data,
    build_operator_template_font_url,
)
from src.domain.types import QueryResult
from src.helpers.bundle import get_table, html_tag_format
from src.helpers.card_urls import GAME_ASSETS_MOUNT_PATH, build_card_url, build_static_url

logger = logging.getLogger(__name__)

STAGE_CARD_REVISION = "stage-v2"

STAGE_TYPE_NAMES = {
    "MAIN": "主线",
    "SUB": "支线",
    "SPECIAL_STORY": "剧情",
    "DAILY": "日常",
    "ACTIVITY": "活动",
    "CAMPAIGN": "剿灭",
    "CLIMB_TOWER": "保全派驻",
}
STAGE_DIFFICULTY_NAMES = {
    "NORMAL": "普通",
    "FOUR_STAR": "突袭",
}
DROP_TYPE_NAMES = {
    "COMPLETE": "首次掉落",
    "NORMAL": "常规掉落",
    "SPECIAL": "特殊掉落",
    "ADDITIONAL": "额外掉落",
    "ONCE": "一次性掉落",
}
OCCURRENCE_NAMES = {
    "ALWAYS": "必定",
    "OFTEN": "较高概率",
    "SOMETIMES": "概率掉落",
    "ALMOST": "低概率",
}
SPECIAL_DROP_NAMES = {
    "CARD_EXP": "作战记录",
    "DIAMOND": "至纯源石",
    "GOLD": "龙门币",
    "TKT_RECRUIT": "招募许可",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("读取关卡 level JSON 失败: %s", path, exc_info=True)
        return {}
    return payload if isinstance(payload, dict) else {}


def _image_data_uri(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if not mime:
        return None
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        logger.warning("读取关卡卡片图片失败: %s", path, exc_info=True)
        return None
    return f"data:{mime};base64,{encoded}"


def _public_asset_url(context: AppContext, relative_path: str) -> str:
    public_path = str(relative_path or "").strip().lstrip("/")
    if public_path.startswith("assets/"):
        public_path = public_path[7:]
    if not public_path:
        return ""
    try:
        return build_static_url(
            cfg=context.cfg,
            relative_path=public_path,
            mount_path=GAME_ASSETS_MOUNT_PATH,
        )
    except RuntimeError:
        return ""


def _clean_text(value: Any) -> str:
    return html_tag_format(str(value or "")).replace("\\n", "\n").strip()


def _stage_level_data(context: AppContext, stage: Stage) -> dict[str, Any]:
    if not stage.level_path:
        return {}

    levels_root = (context.cfg.ResourcePath / "gamedata" / "levels").resolve()
    path = (context.cfg.ResourcePath / "gamedata" / stage.level_path).resolve()
    try:
        if not path.is_relative_to(levels_root):
            logger.warning("拒绝读取越界的关卡 level 路径: %s", stage.level_path)
            return {}
    except OSError:
        return {}
    return _read_json(path)


def _zone_payload(bundle, stage: Stage) -> dict[str, str]:
    table = get_table(bundle.tables, "zone_table", source="gamedata", default={})
    zone = (table.get("zones") or {}).get(stage.zone_id) or {}
    first = str(zone.get("zoneNameFirst") or "").strip()
    second = str(zone.get("zoneNameSecond") or "").strip()
    name = "·".join(item for item in (first, second) if item)
    if not name:
        name = str(zone.get("zoneNameThird") or stage.zone_id).strip()
    return {
        "id": stage.zone_id,
        "name": name,
        "type": str(zone.get("type") or "").strip(),
    }


def _enemy_handbook(bundle) -> dict[str, dict[str, Any]]:
    table = get_table(bundle.tables, "enemy_handbook_table", source="gamedata", default={})
    data = table.get("enemyData") or {}
    return data if isinstance(data, dict) else {}


def _enemy_entry(handbook: dict[str, dict[str, Any]], enemy_id: str) -> dict[str, Any]:
    raw = handbook.get(enemy_id)
    if not isinstance(raw, dict):
        # 部分关卡使用 enemy_xxx_2 / enemy_xxx_3 变体，手册可能只保留基础条目。
        raw = handbook.get(re.sub(r"_(?:2|3|4)$", "", enemy_id)) or {}
    raw = raw if isinstance(raw, dict) else {}
    damage_types = raw.get("damageType") or []
    attack_type = raw.get("attackType")
    if not attack_type:
        attack_type = "/".join(
            {"PHYSIC": "物理", "MAGIC": "法术", "TRUE": "真实"}.get(str(item), str(item))
            for item in damage_types
        )
    return {
        "id": enemy_id,
        "name": str(raw.get("name") or enemy_id).strip(),
        "enemy_level": str(raw.get("enemyLevel") or "NORMAL").strip(),
        "enemy_level_name": {
            "NORMAL": "普通",
            "ELITE": "精英",
            "BOSS": "BOSS",
        }.get(str(raw.get("enemyLevel") or "NORMAL"), str(raw.get("enemyLevel") or "")),
        "attack_type": str(attack_type or "-").strip(),
        "sort_id": int(raw.get("sortId") or 0),
    }


def _build_enemies(bundle, level_data: dict[str, Any]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for wave in level_data.get("waves") or []:
        if not isinstance(wave, dict):
            continue
        for fragment in wave.get("fragments") or []:
            if not isinstance(fragment, dict):
                continue
            for action in fragment.get("actions") or []:
                if not isinstance(action, dict) or action.get("actionType") != "SPAWN":
                    continue
                enemy_id = str(action.get("key") or "").strip()
                if not enemy_id:
                    continue
                counts[enemy_id] = counts.get(enemy_id, 0) + int(action.get("count") or 0)

    refs = {
        str(item.get("id") or "").strip(): item
        for item in (level_data.get("enemyDbRefs") or [])
        if isinstance(item, dict) and item.get("id")
    }
    handbook = _enemy_handbook(bundle)
    result: list[dict[str, Any]] = []
    for enemy_id, count in counts.items():
        item = _enemy_entry(handbook, enemy_id)
        item["count"] = count
        item["ref_level"] = (refs.get(enemy_id) or {}).get("level")
        result.append(item)
    result.sort(key=lambda item: (int(item.get("sort_id") or 0), str(item.get("name") or "")))
    return result


def _item_detail(bundle, item_id: str) -> dict[str, Any]:
    table = get_table(bundle.tables, "item_table", source="gamedata", default={})
    item = (table.get("items") or {}).get(item_id) or {}
    return item if isinstance(item, dict) else {}


def _build_drops(context: AppContext, bundle, stage: Stage) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    raw_items = stage.drop_info.get("displayDetailRewards") or {}
    if not isinstance(raw_items, list):
        return result

    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        drop_type = str(raw.get("dropType") or "").strip()
        item_type = str(raw.get("type") or "").strip()
        detail = _item_detail(bundle, item_id)
        icon_id = str(detail.get("iconId") or "").strip()
        name = str(detail.get("name") or SPECIAL_DROP_NAMES.get(item_type) or item_type or item_id).strip()
        asset_path = f"assets/item/{icon_id}.png" if icon_id else ""
        result.append(
            {
                "id": item_id,
                "name": name,
                "type": item_type,
                "drop_type": drop_type,
                "drop_type_name": DROP_TYPE_NAMES.get(drop_type, drop_type),
                "occurrence": str(raw.get("occPercent") or "").strip(),
                "occurrence_name": OCCURRENCE_NAMES.get(str(raw.get("occPercent") or ""), str(raw.get("occPercent") or "")),
                "icon_id": icon_id,
                "icon_url": _public_asset_url(context, asset_path) if asset_path else "",
            }
        )
    return result


def _map_paths(resource_root: Path, stage_id: str) -> list[Path]:
    map_root = resource_root / "assets" / "map"
    base_id = str(stage_id or "").replace("#f#", "")
    candidates = sorted(
        map_root.glob(f"{base_id}_[0-9]*.png"),
        key=lambda path: (int(path.stem.rsplit("_", 1)[-1]) if path.stem.rsplit("_", 1)[-1].isdigit() else 0, path.name),
    )
    exact = map_root / f"{base_id}.png"
    if candidates:
        return candidates
    if exact.is_file():
        return [exact]

    # easy/tough 关卡通常复用 main 地图；仅在精确资源缺失时回退。
    fallback_id = base_id.replace("easy_", "main_").replace("tough_", "main_")
    fallback = map_root / f"{fallback_id}.png"
    return [fallback] if fallback.is_file() else []


def _build_maps(context: AppContext, stage: Stage) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in _map_paths(context.cfg.ResourcePath, stage.id):
        relative = str(path.relative_to(context.cfg.ResourcePath)).replace("\\", "/")
        result.append(
            {
                "id": path.stem,
                "url": _public_asset_url(context, relative),
            }
        )
    return result


def build_stage_payload(context: AppContext, bundle, stage: Stage) -> dict[str, Any]:
    level_data = _stage_level_data(context, stage)
    options = level_data.get("options") or {}
    maps = _build_maps(context, stage)
    enemies = _build_enemies(bundle, level_data)
    drops = _build_drops(context, bundle, stage)

    return {
        "id": stage.id,
        "code": stage.code,
        "name": stage.name,
        "stage_type": stage.stage_type,
        "stage_type_name": STAGE_TYPE_NAMES.get(stage.stage_type, stage.stage_type),
        "difficulty": stage.difficulty,
        "difficulty_name": STAGE_DIFFICULTY_NAMES.get(stage.difficulty, stage.difficulty),
        "zone": _zone_payload(bundle, stage),
        "danger_level": stage.danger_level,
        "ap_cost": stage.ap_cost,
        "description": stage.description,
        "options": {
            "character_limit": options.get("characterLimit"),
            "max_life_point": options.get("maxLifePoint"),
            "initial_cost": options.get("initialCost"),
            "max_cost": options.get("maxCost"),
        },
        "maps": maps,
        "enemies": enemies,
        "drops": drops,
    }


def build_stage_query_result(context: AppContext, stage_id: str) -> QueryResult | QueryExecutionResult:
    bundle = context.data_repository.get_bundle()
    normalized_id = str(stage_id or "").strip()
    stage = (getattr(bundle, "stages", {}) or {}).get(normalized_id)
    if stage is None:
        return QueryExecutionResult(message=f"未找到关卡ID: {normalized_id}")

    stage_payload = build_stage_payload(context, bundle, stage)
    resource_root = context.cfg.ResourcePath
    map_data: dict[str, str] = {}
    enemy_icon_data: dict[str, str] = {}
    item_icon_data: dict[str, str] = {}

    for map_item in stage_payload["maps"]:
        data = _image_data_uri(resource_root / "assets" / "map" / f"{map_item['id']}.png")
        if data:
            map_data[map_item["id"]] = data
    for enemy in stage_payload["enemies"]:
        data = _image_data_uri(resource_root / "assets" / "enemy" / f"{enemy['id']}.png")
        if data:
            enemy_icon_data[enemy["id"]] = data
    for drop in stage_payload["drops"]:
        icon_id = drop.get("icon_id")
        if not icon_id:
            continue
        data = _image_data_uri(resource_root / "assets" / "item" / f"{icon_id}.png")
        if data:
            item_icon_data[icon_id] = data

    return QueryResult(
        type="stage",
        key=stage.id,
        title=f"{stage.code} {stage.name}".strip(),
        data={
            "stage": stage_payload,
            "map_data": map_data,
            "enemy_icon_data": enemy_icon_data,
            "item_icon_data": item_icon_data,
            "template_bg_data": build_operator_template_bg_data(context.cfg.ProjectRoot),
            "template_font_url": build_operator_template_font_url(context.cfg.ProjectRoot),
        },
    )


async def query_stage_by_id(context: AppContext, stage_id: str) -> QueryExecutionResult:
    normalized_id = str(stage_id or "").strip()
    if not normalized_id:
        return QueryExecutionResult(message="stage_id 不能为空")

    try:
        result = build_stage_query_result(context, normalized_id)
        if isinstance(result, QueryExecutionResult):
            return result

        bundle = context.data_repository.get_bundle()
        bundle_version = getattr(bundle, "version", None) or "v0"
        payload_key = f"stage:{normalized_id}:{bundle_version}:{STAGE_CARD_REVISION}"

        data_url = None
        try:
            await context.card_service.get(
                template="stage",
                payload_key=payload_key,
                payload=result,
                format="json",
            )
            try:
                data_url = build_card_url(
                    cfg=context.cfg,
                    template="stage",
                    payload_key=payload_key,
                    format="json",
                )
            except RuntimeError:
                logger.info("未配置 BaseUrl，关卡 JSON 仅生成本地缓存: stage_id=%s", normalized_id)
        except Exception:
            logger.warning("准备关卡 JSON 产物失败: stage_id=%s", normalized_id, exc_info=True)

        image_url = None
        image_path = None
        try:
            artifact = await context.card_service.get(
                template="stage",
                payload_key=payload_key,
                payload=result,
                format="png",
                params={
                    "viewport": {"width": 1280, "height": 720, "deviceScaleFactor": 1},
                    "full_page": True,
                    "wait_until": "load",
                },
            )
            image_path = str(artifact.path) if context.prefer_local_artifact_path else None
            try:
                image_url = build_card_url(
                    cfg=context.cfg,
                    template="stage",
                    payload_key=payload_key,
                    format="png",
                )
            except RuntimeError:
                logger.info("未配置 BaseUrl，关卡卡片仅生成本地缓存: stage_id=%s", normalized_id)
        except Exception:
            logger.warning("准备关卡卡片失败，仍返回结构化数据和 JSON: stage_id=%s", normalized_id, exc_info=True)

        return QueryExecutionResult(
            data=result.data.get("stage") or {},
            image_url=image_url,
            data_url=data_url,
            image_path=image_path,
        )
    except Exception:
        logger.exception("按 ID 查询关卡失败: stage_id=%s", stage_id)
        return QueryExecutionResult(message="查询关卡信息时发生错误.")
