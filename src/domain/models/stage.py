from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Stage:
    """关卡元数据。

    关卡的 level JSON 体积较大，因此这里只保存元数据和相对文件路径；
    详情查询时再按 level_path 懒加载对应文件。
    """

    id: str = ""
    code: str = ""
    name: str = ""
    stage_type: str = ""
    difficulty: str = ""
    level_id: str = ""
    level_path: str | None = None
    zone_id: str = ""
    description: str = ""
    danger_level: str = ""
    ap_cost: int = 0
    drop_info: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "stage_type": self.stage_type,
            "difficulty": self.difficulty,
            "level_id": self.level_id,
            "zone_id": self.zone_id,
            "description": self.description,
            "danger_level": self.danger_level,
            "ap_cost": self.ap_cost,
        }
