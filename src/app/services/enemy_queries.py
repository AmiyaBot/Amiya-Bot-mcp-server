from __future__ import annotations

import base64
from html import escape
import logging
from pathlib import Path
import re
from typing import Any

from src.app.context import AppContext
from src.app.services.operator_queries import QueryExecutionResult
from src.domain.models.enemy import Enemy
from src.domain.services.operator import build_operator_template_font_url
from src.domain.types import QueryResult
from src.helpers.card_urls import GAME_ASSETS_MOUNT_PATH, build_card_url, build_static_url

logger = logging.getLogger(__name__)

ENEMY_CARD_REVISION = "enemy-v1"
ENEMY_TEMPLATE_BG_PATH = Path("data") / "templates" / "enemy" / "assets" / "pc_bg.jpeg"
ENEMY_TEMPLATE_FALLBACK_ICON_PATH = Path("data") / "templates" / "enemy" / "assets" / "enemy.png"

ENEMY_LEVEL_NAMES = {
    "NORMAL": "普通",
    "ELITE": "精英",
    "BOSS": "BOSS",
}
DAMAGE_TYPE_NAMES = {
    "PHYSIC": "物理",
    "MAGIC": "法术",
    "TRUE": "真实",
    "HEAL": "治疗",
    "NO_DAMAGE": "不攻击",
}
APPLY_WAY_NAMES = {
    "NONE": "不攻击",
    "MELEE": "近战",
    "RANGED": "远程",
    "ALL": "近战/远程",
}
MOTION_NAMES = {
    "WALK": "地面",
    "FLY": "飞行",
}
_ABILITY_TAG_RE = re.compile(r"</>|<\$ba[^>]*>|<@eb\.key>")


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
        logger.warning("读取敌人卡片图片失败: %s", path, exc_info=True)
        return None
    return f"data:{mime};base64,{encoded}"


def _fallback_enemy_icon_data() -> str:
    svg = """
<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180" viewBox="0 0 180 180">
  <rect width="180" height="180" rx="18" fill="#30363b"/>
  <path d="M46 66 67 43l23 15 23-15 21 23-10 20 10 28-25 23H71l-25-23 10-28z" fill="#707980"/>
  <circle cx="69" cy="91" r="8" fill="#ff7a33"/><circle cx="111" cy="91" r="8" fill="#ff7a33"/>
  <path d="M66 118h48" stroke="#dce2e6" stroke-width="8" stroke-linecap="round"/>
</svg>
""".strip()
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _public_enemy_icon_url(context: AppContext, enemy_id: str) -> str:
    icon_path = context.cfg.ResourcePath / "assets" / "enemy" / f"{enemy_id}.png"
    if not icon_path.is_file():
        return ""
    try:
        return build_static_url(
            cfg=context.cfg,
            relative_path=f"enemy/{enemy_id}.png",
            mount_path=GAME_ASSETS_MOUNT_PATH,
        )
    except RuntimeError:
        return ""


def _escape_ability_segment(text: str) -> str:
    return (
        escape(text)
        .replace("\r\n", "<br>")
        .replace("\n", "<br>")
        .replace("；", "；<br>")
        .replace(";", ";<br>")
    )


def _format_ability_html(raw_text: str) -> str:
    """只转换游戏内已知标记，其余文本全部转义。"""
    result: list[str] = []
    stack: list[str] = []
    position = 0
    for match in _ABILITY_TAG_RE.finditer(raw_text):
        result.append(_escape_ability_segment(raw_text[position:match.start()]))
        token = match.group(0)
        if token == "</>":
            if stack:
                result.append(stack.pop())
        elif token.startswith("<$ba"):
            result.append('<span class="mark"><u>')
            stack.append("</u></span>")
        else:
            result.append('<span class="mark">')
            stack.append("</span>")
        position = match.end()
    result.append(_escape_ability_segment(raw_text[position:]))
    while stack:
        result.append(stack.pop())
    return "".join(result)


def _enemy_summary(context: AppContext, enemy: Enemy) -> dict[str, Any]:
    return {
        "id": enemy.id,
        "name": enemy.name,
        "enemy_index": enemy.index,
        "enemy_level": enemy.enemy_level,
        "enemy_level_name": ENEMY_LEVEL_NAMES.get(enemy.enemy_level, enemy.enemy_level),
        "icon_url": _public_enemy_icon_url(context, enemy.id),
    }


def build_enemy_payload(context: AppContext, bundle, enemy: Enemy) -> dict[str, Any]:
    damage_type_names = [DAMAGE_TYPE_NAMES.get(item, item) for item in enemy.damage_types]
    linked_enemies = [
        _enemy_summary(context, linked)
        for enemy_id in enemy.linked_enemy_ids
        if (linked := (bundle.enemies or {}).get(enemy_id)) is not None
    ]
    attributes: list[dict[str, Any]] = []
    for raw in enemy.attributes:
        item = dict(raw)
        item["immunities"] = dict(raw.get("immunities") or {})
        apply_way = str(item.get("apply_way") or "")
        motion = str(item.get("motion") or "")
        item["apply_way_name"] = APPLY_WAY_NAMES.get(apply_way, apply_way)
        item["motion_name"] = MOTION_NAMES.get(motion, motion)
        attributes.append(item)

    return {
        **_enemy_summary(context, enemy),
        "description": enemy.description,
        "damage_types": list(enemy.damage_types),
        "damage_type_names": damage_type_names,
        "attack_type": enemy.attack_type or "/".join(damage_type_names) or "-",
        "races": [dict(item) for item in enemy.races],
        "abilities": [
            {
                "text": str(item.get("text") or ""),
                "text_format": str(item.get("text_format") or "NORMAL"),
            }
            for item in enemy.abilities
        ],
        "attributes": attributes,
        "linked_enemies": linked_enemies,
    }


def build_enemy_query_result(context: AppContext, enemy_id: str) -> QueryResult | QueryExecutionResult:
    bundle = context.data_repository.get_bundle()
    normalized_id = str(enemy_id or "").strip()
    enemy = (getattr(bundle, "enemies", {}) or {}).get(normalized_id)
    if enemy is None:
        return QueryExecutionResult(message=f"未找到敌人ID: {normalized_id}")

    payload = build_enemy_payload(context, bundle, enemy)
    resource_root = context.cfg.ResourcePath
    icon_data: dict[str, str] = {}
    for item in [payload, *payload["linked_enemies"]]:
        item_id = str(item.get("id") or "")
        data = _image_data_uri(resource_root / "assets" / "enemy" / f"{item_id}.png")
        if data:
            icon_data[item_id] = data

    ability_items = [
        {
            "html": _format_ability_html(str(item.get("raw_text") or item.get("text") or "")),
            "text_format": str(item.get("text_format") or "NORMAL"),
        }
        for item in enemy.abilities
    ]

    return QueryResult(
        type="enemy",
        key=enemy.id,
        title=enemy.name,
        data={
            "enemy": payload,
            "ability_items": ability_items,
            "enemy_icon_data": icon_data,
            "fallback_enemy_icon_data": (
                _image_data_uri(context.cfg.ProjectRoot / ENEMY_TEMPLATE_FALLBACK_ICON_PATH)
                or _fallback_enemy_icon_data()
            ),
            "template_bg_data": _image_data_uri(context.cfg.ProjectRoot / ENEMY_TEMPLATE_BG_PATH),
            "template_font_url": build_operator_template_font_url(context.cfg.ProjectRoot),
        },
    )


async def query_enemy_by_id(context: AppContext, enemy_id: str) -> QueryExecutionResult:
    normalized_id = str(enemy_id or "").strip()
    if not normalized_id:
        return QueryExecutionResult(message="enemy_id 不能为空")

    try:
        result = build_enemy_query_result(context, normalized_id)
        if isinstance(result, QueryExecutionResult):
            return result

        bundle = context.data_repository.get_bundle()
        bundle_version = getattr(bundle, "version", None) or "v0"
        payload_key = f"enemy:{normalized_id}:{bundle_version}:{ENEMY_CARD_REVISION}"

        data_url = None
        try:
            await context.card_service.get(
                template="enemy",
                payload_key=payload_key,
                payload=result,
                format="json",
            )
            try:
                data_url = build_card_url(
                    cfg=context.cfg,
                    template="enemy",
                    payload_key=payload_key,
                    format="json",
                )
            except RuntimeError:
                logger.info("未配置 BaseUrl，敌人 JSON 仅生成本地缓存: enemy_id=%s", normalized_id)
        except Exception:
            logger.warning("准备敌人 JSON 产物失败: enemy_id=%s", normalized_id, exc_info=True)

        image_url = None
        image_path = None
        try:
            artifact = await context.card_service.get(
                template="enemy",
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
                    template="enemy",
                    payload_key=payload_key,
                    format="png",
                )
            except RuntimeError:
                logger.info("未配置 BaseUrl，敌人卡片仅生成本地缓存: enemy_id=%s", normalized_id)
        except Exception:
            logger.warning("准备敌人卡片失败，仍返回结构化数据和 JSON: enemy_id=%s", normalized_id, exc_info=True)

        return QueryExecutionResult(
            data=result.data.get("enemy") or {},
            image_url=image_url,
            data_url=data_url,
            image_path=image_path,
        )
    except Exception:
        logger.exception("按 ID 查询敌人失败: enemy_id=%s", enemy_id)
        return QueryExecutionResult(message="查询敌人信息时发生错误.")
