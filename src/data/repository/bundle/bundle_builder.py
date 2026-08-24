# data/loader/bundle_loader.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from src.app.config import Config
from src.data.models.bundle import DataBundle
from src.data.models._operator_impl import OperatorImpl
from src.domain.models.operator import Operator
from src.domain.models.skin import Skin
from src.domain.models.stage import Stage
from src.domain.models.token import Token
from src.helpers.bundle import build_range, get_table, html_tag_format, parse_template, remove_punctuation

log = logging.getLogger(__name__)


def _read_json(path: Path) -> Dict[str, Any]:
    """读不到/解析失败则返回 {}"""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        log.exception("Failed to read json: %s", path)
        return {}


def load_bundle_from_disk(cfg: Config, version: str | None = None) -> DataBundle:
    if cfg.ResourcePath is None:
        raise ValueError("ResourcePath must be configured")
    if cfg.ProjectRoot is None:
        raise ValueError("ProjectRoot must be configured")

    game_root = cfg.ResourcePath / "gamedata"

    # 1) 读取表
    tables: Dict[str, Any] = {}
    tables["gamedata"] = {}
    for name, folder in [
        ("character_table", "excel"),
        ("uniequip_table", "excel"),
        ("battle_equip_table", "excel"),
        ("favor_table", "excel"),
        ("handbook_team_table", "excel"),
        ("handbook_info_table", "excel"),
        ("item_table", "excel"),
        ("stage_table", "excel"),
        ("zone_table", "excel"),
        ("enemy_handbook_table", "excel"),
        ("range_table", "excel"),
        ("skill_table", "excel"),
        ("skin_table", "excel"),
        ("building_data", "excel"),
        ("charword_table", "excel"),
        ("char_meta_table", "excel"),
    ]:
        tables["gamedata"][name] = _read_json(game_root / folder / f"{name}.json") or {}

    # 2) 添加本地表 ProjectRoot/data/local/*.json
    # 这些表用于存放项目本地的自定义数据
    local_tables_path = Path(cfg.ProjectRoot) / "data" / "local"
    tables["local"] = {}
    if local_tables_path.exists() and local_tables_path.is_dir():
        for file in local_tables_path.glob("*.json"):
            table_name = file.stem
            tables["local"][table_name] = _read_json(file) or {}

    # 3) 添加动态表
    tables["amiyabot"] = {}
    tables["amiyabot"]["limit"] = []
    tables["amiyabot"]["unavailable"] = []
    
    # 3) 构建
    tokens, token_name_to_id = _build_token(tables)
    operators, name_to_id, index_to_id = _build_operators(tables)
    skins, skin_name_to_id = _build_skin_index(operators)
    materials, material_name_to_id = _build_materials(tables)
    stages, stage_alias_to_ids = _build_stages(tables, game_root)

    return DataBundle(
        version=version,
        operators=operators,
        tokens=tokens,
        operator_name_to_id=name_to_id,
        operator_index_to_id=index_to_id,
        token_name_to_id=token_name_to_id,
        materials=materials,
        material_name_to_id=material_name_to_id,
        stages=stages,
        stage_alias_to_ids=stage_alias_to_ids,
        skins=skins,
        skin_name_to_id=skin_name_to_id,
        tables=tables,
    )


_STAGE_TYPE_NAMES = {
    "MAIN": "主线",
    "SUB": "支线",
    "SPECIAL_STORY": "剧情",
    "DAILY": "日常",
    "ACTIVITY": "活动",
    "CAMPAIGN": "剿灭",
    "CLIMB_TOWER": "保全派驻",
}
_STAGE_DIFFICULTY_NAMES = {
    "NORMAL": "普通",
    "FOUR_STAR": "突袭",
}


def _stage_level_path(game_root, level_id: Any) -> str | None:
    raw = str(level_id or "").strip().replace("\\", "/").strip("/")
    if not raw:
        return None
    if raw.lower().startswith("levels/"):
        raw = raw[7:]
    relative = Path(raw.lower())
    if relative.suffix != ".json":
        relative = relative.with_suffix(".json")
    candidate = game_root / "levels" / relative
    try:
        if candidate.resolve().is_relative_to((game_root / "levels").resolve()) and candidate.is_file():
            return str(Path("levels") / relative)
    except OSError:
        return None
    return None


def _stage_aliases(stage: Stage) -> list[str]:
    difficulty_name = _STAGE_DIFFICULTY_NAMES.get(stage.difficulty, stage.difficulty)
    values = {
        stage.id,
        stage.code,
        stage.code.upper(),
        stage.code.lower(),
        stage.name,
        remove_punctuation(stage.name),
    }
    if difficulty_name:
        values.update(
            {
                f"{stage.code} {difficulty_name}",
                f"{stage.name} {difficulty_name}",
                f"{stage.code}{difficulty_name}",
                f"{stage.name}{difficulty_name}",
            }
        )
    return [item.strip() for item in values if item and item.strip()]


def _build_stages(tables, game_root) -> tuple[dict[str, Stage], dict[str, list[str]]]:
    stage_table = get_table(tables, "stage_table", source="gamedata", default={})
    raw_stages = stage_table.get("stages") or {}
    stages: dict[str, Stage] = {}
    aliases: dict[str, list[str]] = {}

    for stage_id, raw in raw_stages.items():
        if not isinstance(raw, dict):
            continue
        normalized_id = str(stage_id or "").strip()
        name = str(raw.get("name") or "").strip()
        if not normalized_id or not name:
            continue

        stage = Stage(
            id=normalized_id,
            code=str(raw.get("code") or "").strip(),
            name=name,
            stage_type=str(raw.get("stageType") or "").strip(),
            difficulty=str(raw.get("difficulty") or "").strip(),
            level_id=str(raw.get("levelId") or "").strip(),
            level_path=_stage_level_path(game_root, raw.get("levelId")),
            zone_id=str(raw.get("zoneId") or "").strip(),
            description=html_tag_format(raw.get("description") or "").replace("\\n", "\n").strip(),
            danger_level=str(raw.get("dangerLevel") or "").strip(),
            ap_cost=int(raw.get("apCost") or 0),
            drop_info=raw.get("stageDropInfo") if isinstance(raw.get("stageDropInfo"), dict) else {},
            raw=raw,
        )
        stages[stage.id] = stage

        for alias in _stage_aliases(stage):
            bucket = aliases.setdefault(alias, [])
            if stage.id not in bucket:
                bucket.append(stage.id)

    return stages, aliases


def _material_rarity(value: Any) -> int | None:
    raw = str(value or "").strip()
    if raw.startswith("TIER_"):
        try:
            return int(raw.rsplit("_", 1)[-1])
        except ValueError:
            return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _build_materials(tables) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """从本地解包构建材料详情、加工配方和官方关卡掉落信息。

    这里不访问一图流：
    - 材料基础资料来自 item_table；
    - 加工/制造配方来自 building_data；
    - 关卡名称来自 stage_table；
    - recommend 保留为空，未来可由独立的效率数据源填充。
    """
    item_table = get_table(tables, "item_table", source="gamedata", default={})
    raw_items = item_table.get("items") or {}
    stage_table = get_table(tables, "stage_table", source="gamedata", default={})
    stages = stage_table.get("stages") or {}
    building_data = get_table(tables, "building_data", source="gamedata", default={})

    # 保留所有非潜能信物物品，供配方树解析；搜索索引稍后只收录材料分类。
    materials: Dict[str, Dict[str, Any]] = {}
    material_name_to_id: Dict[str, str] = {}
    for item_id, raw in raw_items.items():
        if not isinstance(raw, dict) or str(item_id).startswith("p_char"):
            continue

        normalized_id = str(item_id)
        name = str(raw.get("name") or "").strip()
        if not name:
            continue

        record = {
            "id": normalized_id,
            "name": name,
            "description": html_tag_format(raw.get("description") or "").strip(),
            "usage": html_tag_format(raw.get("usage") or "").strip(),
            "rarity": _material_rarity(raw.get("rarity")),
            "icon_id": str(raw.get("iconId") or "").strip(),
            "item_type": str(raw.get("itemType") or "").strip(),
            "classify_type": str(raw.get("classifyType") or "").strip(),
            "recipe": [],
            "source": {"main": [], "act": []},
            "recommend": [],
            "recommend_source": "unavailable",
        }
        materials[normalized_id] = record

        # 材料类型以解包的 classifyType 为准，避免统一搜索混入礼包、抽卡券等物品。
        if record["classify_type"] == "MATERIAL":
            material_name_to_id[name] = normalized_id

    # target item_id -> 原料列表。使用公式表直接建索引，避免依赖 item 内可能变化的 formulaId。
    recipes_by_target: Dict[str, list[dict[str, Any]]] = {}
    for process, table_name in (
        ("WORKSHOP", "workshopFormulas"),
        ("MANUFACTURE", "manufactFormulas"),
    ):
        formulas = building_data.get(table_name) or {}
        for formula in formulas.values() if isinstance(formulas, dict) else formulas:
            if not isinstance(formula, dict):
                continue
            target_id = str(formula.get("itemId") or "").strip()
            if not target_id or target_id not in materials:
                continue
            for cost in formula.get("costs") or []:
                if not isinstance(cost, dict):
                    continue
                ingredient_id = str(cost.get("id") or "").strip()
                if not ingredient_id or ingredient_id not in materials:
                    continue
                recipes_by_target.setdefault(target_id, []).append(
                    {
                        "material_id": ingredient_id,
                        "count": int(cost.get("count", 0) or 0),
                        "process": process,
                    }
                )

    def build_recipe(material_id: str, stack: set[str]) -> list[dict[str, Any]]:
        if material_id in stack:
            return []

        result: list[dict[str, Any]] = []
        next_stack = stack | {material_id}
        for ingredient in recipes_by_target.get(material_id, []):
            ingredient_id = ingredient["material_id"]
            item = materials.get(ingredient_id) or {}
            result.append(
                {
                    "material_id": ingredient_id,
                    "name": item.get("name", ingredient_id),
                    "icon_id": item.get("icon_id", ""),
                    "count": ingredient["count"],
                    "process": ingredient["process"],
                    "children": build_recipe(ingredient_id, next_stack),
                }
            )
        return result

    for material_id, record in materials.items():
        record["recipe"] = build_recipe(material_id, set())

        raw_item = raw_items.get(material_id) or {}
        for drop in raw_item.get("stageDropList") or []:
            if not isinstance(drop, dict):
                continue
            stage_id = str(drop.get("stageId") or "").strip()
            if not stage_id:
                continue
            stage = stages.get(stage_id) or {}
            stage_type = str(stage.get("stageType") or "").strip()
            entry = {
                "stage_id": stage_id,
                "code": str(stage.get("code") or stage_id).strip(),
                "name": str(stage.get("name") or stage_id).strip(),
                "stage_type": stage_type,
                "rate": str(drop.get("occPer") or "").strip(),
            }
            bucket = "main" if stage_type == "MAIN" or stage_id.startswith("main_") else "act"
            record["source"][bucket].append(entry)

    return materials, material_name_to_id


def _build_token(tables):
    
    character_table: Dict[str, dict] = tables.get("gamedata", {}).get("character_table") or {}
    range_table: Dict[str, Any] = tables.get("gamedata", {}).get("range_table") or {}
    skill_table: Dict[str, Any] = tables.get("gamedata", {}).get("skill_table") or {}

    tokens: Dict[str, Token] = {}
    token_classes = get_table(tables, "token_classes", source="local", default={})
    types = get_table(tables, "types", source="local", default={})
    sp_type_table = get_table(tables, "sp_type", source="local", default={})
    skill_type_table = get_table(tables, "skill_type", source="local", default={})

    for code, data in character_table.items():
        if not isinstance(data, dict):
            continue
        if str(code).startswith("token_") or data.get("profession") == "TOKEN":
            phases = data.get("phases") or []
            attrs: List[Dict[str, Any]] = []
            for evolve, ph in enumerate(phases):
                rid = ph.get("rangeId")
                grids = (range_table.get(rid) or {}).get("grids")
                range_map = build_range(grids) if grids else "无范围"
                attrs.append(
                    {"evolve": evolve, "range": range_map, "attr": ph.get("attributesKeyFrames")}
                )

            # 天赋：取每个天赋的最终候选，解析 blackboard 模板
            talents: List[Dict[str, Any]] = []
            for item in data.get("talents") or []:
                candidates = item.get("candidates") or []
                if not candidates:
                    continue
                last = candidates[-1]
                name = str(last.get("name") or "").strip()
                if not name:
                    continue
                raw_desc = last.get("description") or ""
                desc = parse_template(last.get("blackboard") or [], raw_desc) if raw_desc else ""
                desc = html_tag_format(desc).replace("\\n", "\n").strip()
                talents.append({"name": name, "description": desc})

            # 技能：取每个技能的最高等级，解析语义字段
            skills: List[Dict[str, Any]] = []
            for sk in data.get("skills") or []:
                sid = sk.get("skillId")
                if not sid:
                    continue
                detail = skill_table.get(sid) or {}
                levels = detail.get("levels") or []
                if not levels:
                    continue
                last = levels[-1]
                spd = last.get("spData") or {}
                raw_sp_type = str(spd.get("spType") or "")
                raw_skill_type = str(last.get("skillType") or "")
                raw_desc = last.get("description") or ""
                desc = parse_template(last.get("blackboard") or [], raw_desc) if raw_desc else ""
                desc = html_tag_format(desc).replace("\\n", "\n").strip()

                # 技能范围：优先技能自身 rangeId，否则回退召唤物基础攻击范围
                skill_range = ""
                rid = last.get("rangeId")
                if rid and rid in range_table:
                    grids = (range_table.get(rid) or {}).get("grids")
                    if grids:
                        skill_range = build_range(grids)
                if not skill_range and attrs:
                    skill_range = attrs[0].get("range") or ""

                skills.append(
                    {
                        "name": str(last.get("name") or "").strip(),
                        "icon": str(detail.get("iconId") or sid),
                        "sp_type": raw_sp_type,
                        "sp_type_name": sp_type_table.get(raw_sp_type, raw_sp_type),
                        "skill_type": raw_skill_type,
                        "skill_type_name": skill_type_table.get(raw_skill_type, raw_skill_type),
                        "init_sp": int(spd.get("initSp") or 0),
                        "sp_cost": int(spd.get("spCost") or 0),
                        "duration": float(last.get("duration") or 0.0),
                        "description": desc,
                        "range": skill_range,
                    }
                )

            tokens[code] = Token(
                id=code,
                name=data.get("name", ""),
                en_name=data.get("appellation", ""),
                description=html_tag_format(data.get("description") or ""),
                classes=token_classes.get(data.get("profession"), "未知"),
                type=types.get(data.get("position"), "未知"),
                attr=attrs,
                talents=talents,
                skills=skills,
            )

    # 召唤物名称索引：中文名/英文名 -> token_id（与 operator_name_to_id 同模式）
    name_to_id: Dict[str, str] = {}
    for code, token in tokens.items():
        if token.name:
            name_to_id[token.name] = code
        if token.en_name and token.en_name != token.name:
            name_to_id[token.en_name] = code

    return tokens, name_to_id

def _build_operators(tables) -> tuple[Dict[str, Operator], Dict[str, str], Dict[str, str]]:
    character_table: Dict[str, dict] = tables.get("gamedata", {}).get("character_table") or {}

    operators: Dict[str, Operator] = {}
    name_to_id: Dict[str, str] = {}
    index_to_id: Dict[str, str] = {}

    # 干员 id 全集，供皮肤异格归属修正判断修正目标是否存在
    known_operator_ids = {str(op_id) for op_id in character_table if str(op_id).startswith("char_")}

    for op_id, data in character_table.items():
        if not isinstance(data, dict):
            continue
        if not str(op_id).startswith("char_"):
            continue

        op = OperatorImpl(op_id, data, tables=tables, is_recruit=False, known_operator_ids=known_operator_ids)
        operators[op_id] = op

        if getattr(op, "name", ""):
            name_to_id[op.name] = op_id
        if getattr(op, "en_name", ""):
            name_to_id[op.en_name] = op_id
        if getattr(op, "index_name", ""):
            index_to_id[op.index_name] = op_id

    return operators, name_to_id, index_to_id


def _build_skin_index(operators: Dict[str, Operator]) -> tuple[Dict[str, Skin], Dict[str, str]]:
    """汇总各干员的皮肤，构建 skin_id -> Skin 字典与 皮肤名 -> skin_id 搜索索引。

    只收录具名皮肤进搜索索引：精英化立绘名字为 初始/精英一/精英二 这类通用词，
    不可能作为检索词，且收录会与干员名 source 产生噪音。
    皮肤名在解包数据中零重名（2026-08 数据验证：488 个具名皮肤无重复）。
    """
    skins: Dict[str, Skin] = {}
    name_to_id: Dict[str, str] = {}
    for op in operators.values():
        for skin in op.skins():
            skins[skin.skin_id] = skin
            if not skin.is_evolve and skin.name:
                name_to_id[skin.name] = skin.skin_id
    return skins, name_to_id

