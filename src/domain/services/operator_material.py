# domain/services/operator_material.py
"""干员材料页面数据组装：精英化材料 + 技能通用升级材料 + 专精材料。

复刻原插件 operatorArchives 的材料卡片数据链路：
- evolveCost（精英化）来自 character_table.phases[].evolveCost；
- 通用升级（Lv2..7）来自 allSkillLvlup[].lvlUpCost（已贴入各 SkillLevel.costs）；
- 专精（Lv8..10）来自 specializeLevelUpData / levelUpCostCond（已贴入各 SkillLevel.costs）。
材料名称与图标经 item_table 关联补全，图标以 base64 data URI 注入模板。
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

from src.app.context import AppContext
from src.domain.models.generic import GoldCost, MaterialCost
from src.domain.models.operator import Operator
from src.domain.services.operator import build_skill_icon_data
from src.domain.types import QueryResult
from src.helpers.bundle import get_table

logger = logging.getLogger(__name__)

MATERIAL_ASSET_PATH = Path("assets") / "item"
MATERIAL_TEMPLATE_ASSET_PATH = Path("data") / "templates" / "operator_material" / "assets"

# 龙门币（GOLD 类型成本）在 item_table 中的 id
GOLD_ITEM_ID = "4001"

EVOLVE_BADGE_NAMES = ("evolve1", "evolve2")
MASTERY_BADGE_NAMES = ("master1", "master2", "master3")

EVOLVE_PHASE_NAMES = {1: "精英一", 2: "精英二"}
MASTERY_NAMES = {1: "专精一", 2: "专精二", 3: "专精三"}


def _build_image_data_uri(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".png":
        mime = "image/png"
    elif suffix == ".webp":
        mime = "image/webp"
    elif suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    else:
        return None

    try:
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime};base64,{payload}"


def _resolve_asset_path(asset_root: Path, icon_name: str) -> Path:
    asset_path = asset_root / icon_name
    if not asset_path.suffix:
        asset_path = asset_path.with_suffix(".png")
    return asset_path


def build_material_icon_data(icon_ids: set[str], resource_root: Path) -> dict[str, str]:
    """按 iconId 读取 resources/assets/item/<iconId>.png 并转 data URI。"""
    asset_root = resource_root / MATERIAL_ASSET_PATH
    result: dict[str, str] = {}

    for icon_name in icon_ids:
        icon_name = str(icon_name or "").strip()
        if not icon_name or icon_name in result:
            continue

        asset_path = _resolve_asset_path(asset_root, icon_name)
        if not asset_path.exists():
            continue

        data_uri = _build_image_data_uri(asset_path)
        if data_uri:
            result[icon_name] = data_uri

    return result


def build_badge_data(badge_names: tuple[str, ...], project_root: Path) -> dict[str, str]:
    """读取 operator_material 模板 assets 下的徽标 PNG 并转 data URI。"""
    asset_root = project_root / MATERIAL_TEMPLATE_ASSET_PATH
    result: dict[str, str] = {}

    for badge_name in badge_names:
        asset_path = _resolve_asset_path(asset_root, badge_name)
        if not asset_path.exists():
            continue

        data_uri = _build_image_data_uri(asset_path)
        if data_uri:
            result[badge_name] = data_uri

    return result


def _item_lookup(tables: dict):
    item_table = get_table(tables, "item_table", source="gamedata", default={})
    items = item_table.get("items") or {}

    def lookup(item_id: str) -> dict | None:
        item_id = str(item_id or "").strip()
        # 跳过潜能信物等 p_char 前缀物品（对齐原插件 init_materials）
        if not item_id or item_id.startswith("p_char"):
            return None
        entry = items.get(item_id)
        if not isinstance(entry, dict):
            return None
        name = str(entry.get("name") or "").strip()
        icon = str(entry.get("iconId") or "").strip()
        if not name:
            return None
        return {"名称": name, "图标": icon}

    return lookup


def _cost_to_material_item(cost, lookup) -> dict | None:
    cost_type = str(getattr(cost, "type", "") or "")
    if isinstance(cost, GoldCost) or cost_type == "GOLD":
        material_id = GOLD_ITEM_ID
    elif isinstance(cost, MaterialCost):
        material_id = cost.material_id
    else:
        # EvolveCostItem 等使用 id 字段的成本结构
        material_id = str(getattr(cost, "material_id", "") or getattr(cost, "id", "") or "")

    base = lookup(material_id)
    if base is None:
        return None
    return {
        "名称": base["名称"],
        "数量": int(getattr(cost, "count", 0) or 0),
        "图标": base["图标"],
    }


def build_evolve_groups(op: Operator, lookup) -> list[dict]:
    """精英化材料分组：仅精英一 / 精英二（phase 0 无材料）。"""
    groups: list[dict] = []
    for phase in getattr(op, "phases", None) or []:
        idx = int(getattr(phase, "phase_index", 0) or 0)
        name = EVOLVE_PHASE_NAMES.get(idx)
        if not name:
            continue

        items = [
            item
            for cost in (phase.evolve_cost or [])
            if (item := _cost_to_material_item(cost, lookup)) is not None
        ]
        if items:
            groups.append({"阶段": name, "材料": items})
    return groups


def build_common_levels(op: Operator, lookup) -> list[dict]:
    """技能通用升级材料（Lv2..7）：干员级数据，已贴入各技能等级，按等级去重。"""
    levels: dict[int, list[dict]] = {}
    for skill in getattr(op, "skills", None) or []:
        for lev in (getattr(skill, "levels", None) or []):
            level_no = int(getattr(lev, "level", 0) or 0)
            if not (2 <= level_no <= 7) or level_no in levels:
                continue
            items = [
                item
                for cost in (lev.costs or [])
                if (item := _cost_to_material_item(cost, lookup)) is not None
            ]
            levels[level_no] = items

    return [
        {"等级": level_no, "材料": items}
        for level_no, items in sorted(levels.items())
    ]


def build_mastery_groups(op: Operator, lookup) -> list[dict]:
    """专精材料（Lv8..10）：按技能分组，专精一 / 二 / 三。"""
    groups: list[dict] = []
    for skill in getattr(op, "skills", None) or []:
        levels = getattr(skill, "levels", None) or []
        if not levels:
            continue

        entry: dict = {"技能名": getattr(skill, "name", "") or "", "技能图标": getattr(skill, "icon", "") or ""}
        has_mastery = False
        for lev in levels:
            level_no = int(getattr(lev, "level", 0) or 0)
            if not (8 <= level_no <= 10):
                continue
            mastery_name = MASTERY_NAMES.get(level_no - 7)
            if not mastery_name:
                continue
            items = [
                item
                for cost in (lev.costs or [])
                if (item := _cost_to_material_item(cost, lookup)) is not None
            ]
            if items:
                entry[mastery_name] = items
                has_mastery = True

        if has_mastery:
            groups.append(entry)
    return groups


def _collect_material_icon_ids(*groups_lists) -> set[str]:
    icon_ids: set[str] = set()

    def walk(items):
        for item in items or []:
            if not isinstance(item, dict):
                continue
            icon = item.get("图标")
            if icon:
                icon_ids.add(str(icon))
            for value in item.values():
                if isinstance(value, list):
                    walk(value)

    for groups in groups_lists:
        walk(groups)
    return icon_ids


def build_operator_material_query_result(ctx: AppContext, op: Operator) -> QueryResult:
    """基于已解析的 Operator 构建材料 QueryResult，不做名称搜索。"""
    bundle = ctx.data_repository.get_bundle()
    lookup = _item_lookup(bundle.tables)

    evolve_groups = build_evolve_groups(op, lookup)
    common_levels = build_common_levels(op, lookup)
    mastery_groups = build_mastery_groups(op, lookup)

    icon_ids = _collect_material_icon_ids(evolve_groups, common_levels, mastery_groups)

    return QueryResult(
        type="operator_material",
        key=op.name,
        title=op.name,
        data={
            "op": op,
            "skin_url": "",
            "evolve_groups": evolve_groups,
            "common_levels": common_levels,
            "mastery_groups": mastery_groups,
            "material_icon_data": build_material_icon_data(icon_ids, ctx.cfg.ResourcePath),
            "evolve_badge_data": build_badge_data(EVOLVE_BADGE_NAMES, ctx.cfg.ProjectRoot),
            "mastery_badge_data": build_badge_data(MASTERY_BADGE_NAMES, ctx.cfg.ProjectRoot),
            "skill_icon_data": build_skill_icon_data(op, ctx.cfg.ResourcePath),
        },
    )
