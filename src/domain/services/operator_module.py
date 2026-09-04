"""干员模组查询的数据组装。

复用 Operator.modules 中已经解析的 uniequip_table / battle_equip_table 数据，
补全模组各级属性、特性与天赋更新、解锁任务及升级材料，并准备卡片资源。
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

from src.app.context import AppContext, get_bundle_resource_root
from src.domain.models.operator import Operator, OperatorModule
from src.domain.services.operator import (
    build_operator_template_bg_data,
    build_operator_template_bg_url,
    build_operator_template_font_url,
)
from src.domain.services.operator_material import (
    build_item_lookup,
    build_material_icon_data,
    cost_to_material_item,
)
from src.domain.types import QueryResult
from src.helpers.bundle import get_table, html_tag_format


MODULE_ASSET_BASE_URL = "https://web.hycdn.cn/arknights/game/assets/uniequip"

MODULE_ATTRIBUTE_NAMES = {
    "max_hp": "最大生命值",
    "atk": "攻击力",
    "def": "防御力",
    "magic_resistance": "法术抗性",
    "attack_speed": "攻击速度",
    "base_attack_time": "攻击间隔",
    "block_cnt": "阻挡数",
    "cost": "部署费用",
    "respawn_time": "再部署时间",
    "max_deck_stack_cnt": "最大部署数量",
}

EVOLVE_PHASE_NAMES = {
    "PHASE_0": "精英零",
    "PHASE_1": "精英一",
    "PHASE_2": "精英二",
}

MODULE_TYPE_NAMES = {
    "INITIAL": "初始模组",
    "ADVANCED": "专属模组",
}

_TEMPLATE_TOKEN_RE = re.compile(r"\{(-?[\w.]+)(?::([^}]+))?\}")


def _asset_url(*segments: str) -> str:
    encoded = "/".join(quote(str(segment or ""), safe="") for segment in segments)
    return f"{MODULE_ASSET_BASE_URL}/{encoded}.png"


def _normalize_number(value: Any) -> int | float | str | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return int(number)
    return number


def _format_template_value(value: Any, format_spec: str | None) -> str:
    normalized = _normalize_number(value)
    if normalized is None:
        return ""
    if format_spec == "0%" and isinstance(normalized, (int, float)):
        return f"{round(float(normalized) * 100)}%"
    return str(normalized)


def format_module_effect(raw_text: Any, blackboard: list[dict[str, Any]] | None = None) -> str:
    """解析模组描述占位符并移除游戏内富文本标签。"""
    text = str(raw_text or "")
    if not text:
        return ""

    values = {
        str(item.get("key") or "").lower(): item.get("valueStr") or item.get("value")
        for item in (blackboard or [])
        if item.get("key")
    }

    def replace(match: re.Match[str]) -> str:
        raw_key = match.group(1)
        format_spec = match.group(2)
        negative = raw_key.startswith("-")
        key = raw_key.lstrip("-").lower()
        if key not in values:
            return match.group(0)
        value = values[key]
        if negative:
            try:
                value = -float(value)
            except (TypeError, ValueError):
                pass
        return _format_template_value(value, format_spec)

    rendered = _TEMPLATE_TOKEN_RE.sub(replace, text)
    return html_tag_format(rendered).replace("\\n", "\n").strip()


def _build_attributes(raw_items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in raw_items or []:
        raw_key = str(item.get("key") or "").strip()
        value = _normalize_number(item.get("value"))
        if not raw_key or value is None:
            continue
        result.append(
            {
                "key": raw_key,
                "name": MODULE_ATTRIBUTE_NAMES.get(raw_key, raw_key),
                "value": value,
            }
        )
    return result


def _build_effects(
    parts: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    trait_updates: list[dict[str, Any]] = []
    talent_updates: list[dict[str, Any]] = []

    for part in parts or []:
        target = "召唤物" if part.get("isToken") else "干员"
        trait_candidates = ((part.get("overrideTraitDataBundle") or {}).get("candidates") or [])
        for candidate in trait_candidates:
            blackboard = candidate.get("blackboard") or []
            for field in ("additionalDescription", "overrideDescripton"):
                description = format_module_effect(candidate.get(field), blackboard)
                if description:
                    trait_updates.append(
                        {
                            "target": target,
                            "description": description,
                            "potential_rank": int(candidate.get("requiredPotentialRank", 0) or 0) + 1,
                        }
                    )

        talent_candidates = ((part.get("addOrOverrideTalentDataBundle") or {}).get("candidates") or [])
        for candidate in talent_candidates:
            description = format_module_effect(
                candidate.get("upgradeDescription") or candidate.get("description"),
                candidate.get("blackboard") or [],
            )
            name = str(candidate.get("name") or "").strip()
            if not name and not description:
                continue
            talent_updates.append(
                {
                    "target": target,
                    "name": name,
                    "description": description,
                    "potential_rank": int(candidate.get("requiredPotentialRank", 0) or 0) + 1,
                }
            )

    trait_updates = _dedupe_effects(trait_updates)
    talent_updates = _dedupe_effects(talent_updates)
    return trait_updates, talent_updates, _pick_card_talents(talent_updates)


def _dedupe_effects(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in items:
        identity = tuple(item.get(key) for key in ("target", "name", "description", "potential_rank"))
        if identity in seen:
            continue
        seen.add(identity)
        result.append(item)
    return result


def _pick_card_talents(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """与参考卡一致：同名天赋在卡片上展示最高潜能候选，API 仍返回全部候选。"""
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (str(item.get("target") or ""), str(item.get("name") or ""))
        current = selected.get(key)
        if current is None or int(item.get("potential_rank", 0) or 0) >= int(
            current.get("potential_rank", 0) or 0
        ):
            selected[key] = item
    return list(selected.values())


def _build_token_attributes(raw: Any, token_names: dict[str, str]) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    result: list[dict[str, Any]] = []
    for token_id, attributes in raw.items():
        result.append(
            {
                "token_id": str(token_id),
                "token_name": token_names.get(str(token_id), str(token_id)),
                "attributes": _build_attributes(attributes),
            }
        )
    return result


def _build_level_costs(module: OperatorModule, lookup) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {}
    for level_cost in module.level_costs or []:
        items = [
            item
            for cost in level_cost.costs
            if (item := cost_to_material_item(cost, lookup)) is not None
        ]
        result[int(level_cost.level)] = items
    return result


def _build_favor_percent_lookup(tables: dict[str, Any]) -> dict[int, int]:
    favor_table = get_table(tables, "favor_table", source="gamedata", default={})
    result: dict[int, int] = {}
    for frame in (favor_table or {}).get("favorFrames") or []:
        data = (frame or {}).get("data") or {}
        favor_point = data.get("favorPoint")
        percent = data.get("percent")
        if favor_point is None or percent is None:
            continue
        result[int(favor_point)] = int(percent)
    return result


def _build_level_favor(
    module: OperatorModule,
    level: int,
    favor_percent_by_point: dict[int, int],
) -> int | None:
    raw_value = (module.unlock_favors or {}).get(str(level))
    if raw_value is None:
        return None
    favor_point = int(raw_value or 0)
    return favor_percent_by_point.get(favor_point)


def _build_module_entry(
    module: OperatorModule,
    lookup,
    token_names: dict[str, str],
    favor_percent_by_point: dict[int, int],
) -> dict[str, Any]:
    costs_by_level = _build_level_costs(module, lookup)
    phases: list[dict[str, Any]] = []
    for phase in (module.battle_detail or {}).get("phases") or []:
        level = int(phase.get("equipLevel", 0) or 0)
        traits, talents, card_talents = _build_effects(phase.get("parts") or [])
        phases.append(
            {
                "level": level,
                "favor_percent": _build_level_favor(
                    module,
                    level,
                    favor_percent_by_point,
                ),
                "attributes": _build_attributes(phase.get("attributeBlackboard") or []),
                "token_attributes": _build_token_attributes(
                    phase.get("tokenAttributeBlackboard") or {},
                    token_names,
                ),
                "trait_updates": traits,
                "talent_updates": talents,
                "card_talent_updates": card_talents,
                "materials": costs_by_level.get(level, []),
            }
        )

    missions = [
        {
            "id": mission.mission_id,
            "description": str((mission.data or {}).get("desc") or "").strip(),
        }
        for mission in module.missions or []
    ]

    type_code = "-".join(
        part for part in (module.type_name1, module.type_name2) if str(part or "").strip()
    )
    return {
        "id": module.module_id,
        "name": module.name,
        "description": module.desc,
        "type": module.type,
        "type_name": MODULE_TYPE_NAMES.get(module.type, module.type),
        "type_code": type_code or module.type_icon.upper(),
        "type_icon": module.type_icon,
        "module_icon_url": _asset_url(module.icon),
        "type_icon_url": _asset_url("type", "icon", module.type_icon),
        "shining_url": _asset_url("type", "shining", module.shining_color) if module.shining_color else "",
        "accent_color": module.char_color or "#ff9800",
        "show_condition": {
            "phase": EVOLVE_PHASE_NAMES.get(module.show_evolve_phase, module.show_evolve_phase),
            "level": module.show_level,
        },
        "unlock_condition": {
            "phase": EVOLVE_PHASE_NAMES.get(module.unlock_evolve_phase, module.unlock_evolve_phase),
            "level": module.unlock_level,
            "favor": _build_level_favor(module, 1, favor_percent_by_point),
            "missions": missions,
        },
        "phases": phases,
    }


def _collect_material_icon_ids(module_entries: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("图标"))
        for module in module_entries
        for phase in module.get("phases") or []
        for item in phase.get("materials") or []
        if item.get("图标")
    }


def build_operator_module_query_result(ctx: AppContext, op: Operator) -> QueryResult:
    """基于已解析的 Operator 构建模组 QueryResult，不做名称搜索。"""
    bundle = ctx.data_repository.get_bundle()
    lookup = build_item_lookup(bundle.tables)
    token_names = {
        str(token_id): str(getattr(token, "name", "") or token_id)
        for token_id, token in (bundle.tokens or {}).items()
    }
    favor_percent_by_point = _build_favor_percent_lookup(bundle.tables)
    module_entries = [
        _build_module_entry(module, lookup, token_names, favor_percent_by_point)
        for module in (op.modules or [])
    ]
    icon_ids = _collect_material_icon_ids(module_entries)

    return QueryResult(
        type="operator_module",
        key=op.name,
        title=f"{op.name} 的模组",
        data={
            "op": op,
            "modules": module_entries,
            "material_icon_data": build_material_icon_data(icon_ids, get_bundle_resource_root(bundle, ctx)),
            "template_bg_data": build_operator_template_bg_data(ctx.cfg.ProjectRoot),
            "template_bg_url": build_operator_template_bg_url(ctx.cfg.ProjectRoot),
            "template_font_url": build_operator_template_font_url(ctx.cfg.ProjectRoot),
        },
    )
