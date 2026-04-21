from __future__ import annotations
import base64
import logging
from pathlib import Path
import re

from src.helpers.gamedata.search import build_sources, search_source_spec

from src.helpers.bundle import get_table, html_tag_format

from src.app.context import AppContext
from src.domain.models.operator import Operator
from src.domain.types import QueryResult
from src.helpers.glossary import mark_glossary_used_terms

logger = logging.getLogger(__name__)
SKILL_ASSET_PATH = Path("assets") / "skill"
BUILDING_SKILL_ASSET_PATH = Path("assets") / "building_skill"
MODULE_ATTR_KEY_MAP = {
    "max_hp": "maxHp",
    "atk": "atk",
    "def": "def",
    "defense": "def",
    "magic_resistance": "magicResistance",
    "attack_speed": "attackSpeed",
    "base_attack_time": "baseAttackTime",
    "block_cnt": "blockCnt",
    "cost": "cost",
    "respawn_time": "respawnTime",
}

class OperatorNotFoundError(ValueError):
    pass


def build_potential_list(op, tables) -> list[dict]:
    character_table = get_table(tables, "character_table", source="gamedata", default={})
    raw_list = (character_table.get(op.id) or {}).get("potentialRanks") or []
    result = []
    for index, item in enumerate(raw_list):
        description = str(item.get("description") or "").strip()
        if not description:
            continue
        result.append(
            {
                "potential_rank": index,
                "potential_desc": description,
            }
        )
    return result


def build_building_skills(op, tables) -> list[dict]:
    building_data = get_table(tables, "building_data", source="gamedata", default={})
    char_entry = (building_data.get("chars") or {}).get(op.id) or {}
    buff_table = building_data.get("buffs") or {}

    result = []
    for buff_group in char_entry.get("buffChar") or []:
        for buff in buff_group.get("buffData") or []:
            buff_id = buff.get("buffId")
            detail = buff_table.get(buff_id) or {}
            name = str(detail.get("buffName") or "").strip()
            desc = html_tag_format(str(detail.get("description") or "")).replace("\\n", "\n").strip()
            if not name and not desc:
                continue

            cond = buff.get("cond") or {}
            phase_raw = str(cond.get("phase") or "")
            match = re.search(r"(\d+)$", phase_raw)
            phase_num = int(match.group(1)) if match else 0

            result.append(
                {
                    "bs_unlocked": phase_num,
                    "bs_name": name,
                    "bs_desc": desc,
                    "bs_icon": str(detail.get("skillIcon") or ""),
                    "bs_room_type": str(detail.get("roomType") or ""),
                }
            )
    return result

def build_base_attr(op) -> dict:
    """
    返回模板使用的基础属性 dict（key 与旧模板一致）
    """
    if not op.phases:
        return {}

    last_phase = op.phases[-1]
    frame = last_phase.max_frame
    if not frame:
        return {}

    a = frame.data  # OperatorAttributes

    return {
        "maxHp": a.max_hp,
        "atk": a.atk,
        "def": a.defense,
        "magicResistance": a.magic_resistance,
        "attackSpeed": a.attack_speed,
        "baseAttackTime": a.base_attack_time,
        "blockCnt": a.block_cnt,
        "cost": a.cost,
        "respawnTime": a.respawn_time,
    }


def build_trust_attr(op) -> dict:
    """
    信赖满级（50）的加成
    """
    frames = getattr(op, "favorKeyFrames", None)
    if not frames:
        return {}

    # 找 level=50 的
    f = next((x for x in frames if x["level"] == 50), None)
    if not f:
        return {}

    d = f.get("data", {})
    return {
        "maxHp": d.get("maxHp", 0),
        "atk": d.get("atk", 0),
        "def": d.get("def", 0),
    }


def _normalize_attr_value(value: object) -> int | float | object:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value

    if number.is_integer():
        return int(number)
    return number


def build_module_attr(op) -> dict:
    modules = getattr(op, "modules", None) or []
    for module in reversed(modules):
        phases = (getattr(module, "battle_detail", {}) or {}).get("phases") or []
        if not phases:
            continue

        attr_board = (phases[-1] or {}).get("attributeBlackboard") or []
        result: dict[str, int | float | object] = {}
        for item in attr_board:
            raw_key = str(item.get("key") or "").strip()
            target_key = MODULE_ATTR_KEY_MAP.get(raw_key)
            if not target_key:
                continue

            value = _normalize_attr_value(item.get("value"))
            if value in (None, ""):
                continue

            existing = result.get(target_key)
            if isinstance(existing, (int, float)) and isinstance(value, (int, float)):
                result[target_key] = _normalize_attr_value(existing + value)
            else:
                result[target_key] = value

        if result:
            return result

    return {}


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


def build_skill_icon_data(op, resource_root: Path) -> dict[str, str]:
    asset_root = resource_root / SKILL_ASSET_PATH
    result: dict[str, str] = {}

    for skill in op.skills or []:
        icon_name = str(getattr(skill, "icon", "") or "").strip()
        if not icon_name or icon_name in result:
            continue

        asset_path = asset_root / icon_name
        if not asset_path.suffix:
            asset_path = asset_path.with_suffix(".png")
        if not asset_path.exists():
            continue

        data_uri = _build_image_data_uri(asset_path)
        if data_uri:
            result[icon_name] = data_uri

    return result


def build_building_skill_icon_data(items: list[dict], resource_root: Path) -> dict[str, str]:
    asset_root = resource_root / BUILDING_SKILL_ASSET_PATH
    result: dict[str, str] = {}

    for item in items:
        icon_name = str(item.get("bs_icon") or "").strip()
        if not icon_name or icon_name in result:
            continue

        asset_path = asset_root / icon_name
        if not asset_path.suffix:
            asset_path = asset_path.with_suffix(".png")
        if not asset_path.exists():
            continue

        data_uri = _build_image_data_uri(asset_path)
        if data_uri:
            result[icon_name] = data_uri

    return result


def search_operator_by_name(ctx: AppContext, name: str) -> QueryResult:

    search_sources = build_sources(ctx.data_repository.get_bundle(), source_key=["name"])
    search_results = search_source_spec(
        name,
        sources=search_sources
    )

    if not search_results:
        raise OperatorNotFoundError(f"未找到干员: {name}")
    elif len(search_results.matches) > 1:
        # 交互式选择结果
        matched_names = [m.matched_text for m in search_results.matches if m.key == "name"]
        # return f"❌ 找到多个匹配的干员名称: {', '.join(matched_names)}，请提供更精确的名称。"
        raise OperatorNotFoundError(f"未找到干员: {name}")
    
    op: Operator = search_results.by_key("name")[0].value

    last_phase = op.phases[-1]

    bundle = ctx.data_repository.get_bundle()
    CLASSICON = get_table(bundle.tables, "classes_icons", source="local")
    SP_TYPE_NAME = get_table(bundle.tables, "sp_type", source="local")
    SKILL_TYPE_NAME = get_table(bundle.tables, "skill_type", source="local")
    building_skills = build_building_skills(op, bundle.tables)
    result = QueryResult(
        type="operator_profile",
        key=op.name,
        title=op.name,
        data={
            "op": op,
            "skin_url": "",  # 你自己拼
            "base_attr": build_base_attr(op),
            "trust_attr": build_trust_attr(op),
            "module_attr": build_module_attr(op),
            "op_range_html": None,  # 后面补
            "skill_range_html": {},
            "skill_icon_data": build_skill_icon_data(op, ctx.cfg.ResourcePath),
            "building_skill_icon_data": build_building_skill_icon_data(building_skills, ctx.cfg.ResourcePath),
            "classes_icons": CLASSICON,
            "sp_type_name": SP_TYPE_NAME,
            "skill_type_name": SKILL_TYPE_NAME,
            "talents_list": op.talents(),
            "building_skills": building_skills,
            "potential_list": build_potential_list(op, bundle.tables),
        }
    )
    return result