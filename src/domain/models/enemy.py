from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Enemy:
    """敌方单位的可检索元数据与已解析等级属性。"""

    id: str = ""
    index: str = ""
    name: str = ""
    enemy_level: str = ""
    description: str = ""
    attack_type: str = ""
    damage_types: list[str] = field(default_factory=list)
    races: list[dict[str, str]] = field(default_factory=list)
    abilities: list[dict[str, str]] = field(default_factory=list)
    attributes: list[dict[str, Any]] = field(default_factory=list)
    linked_enemy_ids: list[str] = field(default_factory=list)
    sort_id: int = 0
    hide_in_handbook: bool = False
    hide_in_stage: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

