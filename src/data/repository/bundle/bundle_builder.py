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
from src.domain.models.token import Token
from src.helpers.bundle import build_range, get_table, html_tag_format

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
        ("handbook_team_table", "excel"),
        ("item_table", "excel"),
        ("range_table", "excel"),
        ("skill_table", "excel"),
        ("skin_table", "excel"),
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
    tokens = _build_token(tables)
    operators, name_to_id, index_to_id = _build_operators(tables)

    return DataBundle(
        version=version,
        operators=operators,
        tokens=tokens,
        operator_name_to_id=name_to_id,
        operator_index_to_id=index_to_id,
        tables=tables,
    )


def _build_token(tables):
    
    character_table: Dict[str, dict] = tables.get("gamedata", {}).get("character_table") or {}
    range_table: Dict[str, Any] = tables.get("gamedata", {}).get("range_table") or {}

    tokens: Dict[str, Token] = {}
    token_classes = get_table(tables, "token_classes", source="local", default={})
    types = tables.get("types", {}) or {}

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

            tokens[code] = Token(
                id=code,
                name=data.get("name", ""),
                en_name=data.get("appellation", ""),
                description=html_tag_format(data.get("description") or ""),
                classes=token_classes.get(data.get("profession"), "未知"),
                type=types.get(data.get("position"), "未知"),
                attr=attrs,
            )
    
    return tokens

def _build_operators(tables) -> tuple[Dict[str, Operator], Dict[str, str], Dict[str, str]]:
    character_table: Dict[str, dict] = tables.get("gamedata", {}).get("character_table") or {}

    operators: Dict[str, Operator] = {}
    name_to_id: Dict[str, str] = {}
    index_to_id: Dict[str, str] = {}

    for op_id, data in character_table.items():
        if not isinstance(data, dict):
            continue
        if not str(op_id).startswith("char_"):
            continue

        op = OperatorImpl(op_id, data, tables=tables, is_recruit=False)
        operators[op_id] = op

        if getattr(op, "name", ""):
            name_to_id[op.name] = op_id
        if getattr(op, "en_name", ""):
            name_to_id[op.en_name] = op_id
        if getattr(op, "index_name", ""):
            index_to_id[op.index_name] = op_id

    return operators, name_to_id, index_to_id




