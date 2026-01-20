from __future__ import annotations
import logging

from src.helpers.gamedata.search import build_sources, search_source_spec

from src.helpers.bundle import get_table

from src.app.context import AppContext
from src.domain.models.operator import Operator
from src.domain.types import QueryResult
from src.helpers.glossary import mark_glossary_used_terms

logger = logging.getLogger(__name__)

class OperatorNotFoundError(ValueError):
    pass

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
    result = QueryResult(
        type="operator_profile",
        key=op.name,
        title=op.name,
        data={
            "op": op,
            "skin_url": "",  # 你自己拼
            "base_attr": build_base_attr(op),
            "trust_attr": build_trust_attr(op),
            "module_attr": {},  # 先空
            "op_range_html": None,  # 后面补
            "skill_range_html": {},
            "classes_icons": CLASSICON,
            "sp_type_name": SP_TYPE_NAME,
            "skill_type_name": SKILL_TYPE_NAME,
            "talents_list": op.talents(),
            "building_skills": [],
            "potential_list": [],
        }
    )
    return result