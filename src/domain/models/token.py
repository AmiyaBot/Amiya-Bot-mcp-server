# domain/models/token.py
from dataclasses import dataclass, field
from typing import Any, Dict, List

STR_DICT = Dict[str, Any]
LIST_STR_DICT = List[STR_DICT]


@dataclass(slots=True)
class Token:
    """
    召唤物 / 装置 / Token 的领域模型（轻量）
    - 不负责 IO
    - 不负责 JSON 解析（解析在 data/loader 或 factory 中做）
    """

    id: str = ""
    name: str = ""
    en_name: str = ""
    description: str = ""

    classes: str = ""     # 职业/分支（如果你有更严格枚举可替换）
    type: str = ""        # token 类型

    attr: LIST_STR_DICT = field(default_factory=list)

    talents: LIST_STR_DICT = field(default_factory=list)
    """召唤物天赋（语义化）：[{"name": 名称, "description": 描述}]"""

    skills: LIST_STR_DICT = field(default_factory=list)
    """召唤物技能（语义化）：[{"name", "sp_type", "sp_type_name", "skill_type", "skill_type_name", "init_sp", "sp_cost", "duration", "description"}]"""

    # 可选：保留原始字段兜底（不建议 core 直接用它，但方便调试/兼容）
    raw: STR_DICT = field(default_factory=dict, repr=False)

    def to_dict(self) -> STR_DICT:
        """稳定的对外序列化（给 json renderer / toolcall）"""
        return {
            "id": self.id,
            "name": self.name,
            "en_name": self.en_name,
            "description": self.description,
            "classes": self.classes,
            "type": self.type,
            "attr": self.attr,
            "talents": self.talents,
            "skills": self.skills,
        }
