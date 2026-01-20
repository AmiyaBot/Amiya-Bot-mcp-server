# domain/models/operator.py
from __future__ import annotations
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Any, Optional

from src.domain.models.generic import Cost, MaterialCost, parse_cost

STR_DICT = Dict[str, Any]
LIST_STR_DICT = List[STR_DICT]

class Operator(ABC):
    """
    干员领域模型（接口定义）
    """

    def __init__(self):
        # ---- 基础标识 ----
        self.id: str = ""
        """干员 ID（唯一标识符）"""
        self.name: str = ""
        """干员名称"""
        self.en_name: str = ""
        """干员英文名"""
        self.wiki_name: str = ""
        """干员维基名称"""
        self.index_name: str = ""
        """干员索引名称（无标点）"""
        self.origin_name: str = ""
        """干员真名（如果有）"""

        # ---- ??? ----
        self.number: str = ""

        # ---- 分类与属性 ----
        self.rarity: int = 0
        """干员稀有度（1-6）"""
        self.classes: str = ""
        """干员职业（中文）, 如“先锋”"""
        self.classes_sub: str = ""
        """干员子职业（中文）, 如“领主”"""
        self.classes_code: str = ""
        """干员职业代码，如“VANGUARD”"""
        self.type: str = ""
        """干员类型（中文）, 如“近战位”"""
        self.tags: List[str] = []
        """干员标签列表，如“新手”、“召唤”"""
        self.range: str = ""
        """干员攻击范围描述"""

        # ---- 人物信息 ----
        self.sex: str = ""
        """性别"""
        self.race: str = ""
        """种族"""
        self.cv: Dict[str, str] = {}
        """声优信息，格式如 {"中文": "某某", "日文": "某某"}，如果存在多个声优则以半角逗号分隔"""
        self.drawer: str = ""
        """画师"""

        # ---- 阵营 ----
        self.team_id: str = ""
        """主阵营 ID"""
        self.team: str = ""

        self.nation_id: str = ""
        """国家/势力 ID"""
        self.nation: str = ""
        """国家/势力 名称"""

        self.group_id: str = ""
        """集团 ID"""
        self.group: str = ""
        """主阵营名称"""

        # ---- 其他 ----
        self.birthday: str = ""
        """生日，格式如 "MM-DD" """
        self.profile: str = ""
        """干员档案/简介"""
        self.impression: str = ""
        """干员印象"""
        self.potential_item: str = ""
        """潜能物品"""

        self.limit: bool = False
        """是否为限定干员"""
        self.unavailable: bool = False
        """是否为不可获取干员"""
        self.is_recruit: bool = False
        """是否可通过公开招募获取"""
        self.is_classic: bool = False
        """是否为中坚干员"""
        self.is_sp: bool = False
        """是否为特殊干员"""
        
        # ---- Detail（扁平化字段）----
        self.operator_trait: str = ""
        """特性描述（已格式化）"""
        self.operator_usage: str = ""
        """档案用途/使用说明"""
        self.operator_quote: str = ""
        """档案描述/印象（你旧逻辑里的 itemDesc）"""
        self.operator_token: str = ""
        """召唤物/信物描述（若有）"""
        self.max_level: str = ""
        """最大精英化阶段与等级，如 '2 - 90' """

        # ---- 结构化数据 ----

        self.phases: List[OperatorPhase] = []
        """精英化阶段信息（结构化）"""

        self.skills: List[Skill] = []
        """技能信息（结构化）"""

        self.modules: List[OperatorModule] = []
        """模组信息（结构化）"""

    # ========== 对外稳定接口 ==========

    @abstractmethod
    def talents(self) -> LIST_STR_DICT:
        raise NotImplementedError

    @abstractmethod
    def skins(self) -> LIST_STR_DICT:
        raise NotImplementedError

    @abstractmethod
    def voices(self) -> LIST_STR_DICT:
        raise NotImplementedError


@dataclass(frozen=True)
class OperatorAttributes:
    # 你样例里最常用的一批；其余字段走 extra 保存，避免丢数据
    max_hp: int = 0
    atk: int = 0
    defense: int = 0
    magic_resistance: float = 0.0
    cost: int = 0
    block_cnt: int = 0
    move_speed: float = 0.0
    attack_speed: float = 0.0
    base_attack_time: float = 0.0
    respawn_time: int = 0

    # 可选：把你不想显式建模的字段兜底放这里（比如各种 immune、tauntLevel 等）
    extra: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_gamedata(d: Dict[str, Any]) -> "OperatorAttributes":
        d = d or {}
        known = {
            "maxHp", "atk", "def", "magicResistance", "cost", "blockCnt",
            "moveSpeed", "attackSpeed", "baseAttackTime", "respawnTime",
        }
        extra = {k: v for k, v in d.items() if k not in known}

        return OperatorAttributes(
            max_hp=int(d.get("maxHp", 0) or 0),
            atk=int(d.get("atk", 0) or 0),
            defense=int(d.get("def", 0) or 0),
            magic_resistance=float(d.get("magicResistance", 0.0) or 0.0),
            cost=int(d.get("cost", 0) or 0),
            block_cnt=int(d.get("blockCnt", 0) or 0),
            move_speed=float(d.get("moveSpeed", 0.0) or 0.0),
            attack_speed=float(d.get("attackSpeed", 0.0) or 0.0),
            base_attack_time=float(d.get("baseAttackTime", 0.0) or 0.0),
            respawn_time=int(d.get("respawnTime", 0) or 0),
            extra=extra,
        )


@dataclass(frozen=True)
class OperatorAttributeFrame:
    level: int
    data: OperatorAttributes

    @staticmethod
    def from_gamedata(d: Dict[str, Any]) -> "OperatorAttributeFrame":
        d = d or {}
        return OperatorAttributeFrame(
            level=int(d.get("level", 0) or 0),
            data=OperatorAttributes.from_gamedata(d.get("data") or {}),
        )


@dataclass(frozen=True)
class EvolveCostItem:
    id: str
    count: int
    type: str  # "MATERIAL" 等

    @staticmethod
    def from_gamedata(d: Dict[str, Any]) -> "EvolveCostItem":
        d = d or {}
        return EvolveCostItem(
            id=str(d.get("id") or ""),
            count=int(d.get("count", 0) or 0),
            type=str(d.get("type") or ""),
        )


@dataclass(frozen=True)
class OperatorPhase:
    """
    对应 character_table 里的 phases[i]
    """
    phase_index: int                 # 0/1/2
    character_prefab_key: str
    range_id: str
    max_level: int
    attributes: List[OperatorAttributeFrame] = field(default_factory=list)
    evolve_cost: List[EvolveCostItem] = field(default_factory=list)

    @property
    def min_frame(self) -> Optional[OperatorAttributeFrame]:
        return self.attributes[0] if self.attributes else None

    @property
    def max_frame(self) -> Optional[OperatorAttributeFrame]:
        return self.attributes[-1] if self.attributes else None

    @staticmethod
    def from_gamedata(phase_index: int, d: Dict[str, Any]) -> "OperatorPhase":
        d = d or {}
        frames = [OperatorAttributeFrame.from_gamedata(x) for x in (d.get("attributesKeyFrames") or [])]
        costs = [EvolveCostItem.from_gamedata(x) for x in (d.get("evolveCost") or [])] if d.get("evolveCost") else []

        return OperatorPhase(
            phase_index=phase_index,
            character_prefab_key=str(d.get("characterPrefabKey") or ""),
            range_id=str(d.get("rangeId") or ""),
            max_level=int(d.get("maxLevel", 0) or 0),
            attributes=frames,
            evolve_cost=costs,
        )
    

@dataclass(frozen=True)
class SkillLevel:
    level: int                 # 1..7（普通） / 8..10（专精）
    mastery: int               # 0=普通升级，1..3=专精
    name: str
    skill_type: str
    duration: float
    duration_type: str
    range: str
    description: str
    sp: SkillSpData
    costs: List[Cost] = field(default_factory=list)

@dataclass(frozen=True)
class Skill:
    skill_id: str
    skill_index: int
    icon: str
    name: str
    levels: List[SkillLevel]


@dataclass(frozen=True)
class SkillSpData:
    sp_type: str = ""
    init_sp: int = 0
    sp_cost: int = 0
    max_charge_time: int = 0
    increment: float = 0.0


@dataclass(frozen=True)
class ModuleMission:
    mission_id: str
    data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_gamedata(mission_id: str, mission_dict: Dict[str, Any]) -> "ModuleMission":
        return ModuleMission(
            mission_id=str(mission_id or ""),
            data=dict(mission_dict or {}),
        )

@dataclass(frozen=True)
class ModuleLevelCost:
    level: int
    costs: list[Cost]

@dataclass(frozen=True)
class OperatorModule:
    """
    对应 uniequip_table.equipDict[mid] + battle_equip_table[mid] + missionList 映射
    """
    module_id: str
    name: str = ""
    icon: str = ""
    desc: str = ""
    type: str = ""                 # INITIAL / ADVANCED 等
    type_icon: str = ""
    type_name1: str = ""
    type_name2: Optional[str] = None

    show_evolve_phase: str = ""
    unlock_evolve_phase: str = ""
    show_level: int = 0
    unlock_level: int = 0

    char_id: str = ""
    char_equip_order: int = 0
    has_unlock_mission: bool = False
    is_special_equip: bool = False
    char_color: str = ""

    mission_ids: List[str] = field(default_factory=list)
    missions: List[ModuleMission] = field(default_factory=list)

    unlock_favors: Dict[str, Any] = field(default_factory=dict)
    level_costs: list[ModuleLevelCost] = field(default_factory=list)

    battle_detail: Dict[str, Any] = field(default_factory=dict)  # battle_equip_table[mid] 原样存一份（稳定后可再结构化）

    @staticmethod
    def from_gamedata(
        base: Dict[str, Any],
        battle_detail: Optional[Dict[str, Any]] = None,
        mission_dict: Optional[Dict[str, Any]] = None,
    ) -> "OperatorModule":
        base = base or {}
        battle_detail = battle_detail or {}
        mission_dict = mission_dict or {}

        mid = str(base.get("uniEquipId") or "")
        mids = [str(x) for x in (base.get("missionList") or [])]

        missions = []
        for msid in mids:
            if msid in mission_dict:
                missions.append(ModuleMission.from_gamedata(msid, mission_dict.get(msid) or {}))

        level_costs = []

        raw_cost = base.get("itemCost") or {}
        for level_str, cost_list in raw_cost.items():
            try:
                level = int(level_str)
            except ValueError:
                continue

            costs = [parse_cost(c) for c in (cost_list or [])]
            level_costs.append(ModuleLevelCost(level=level, costs=costs))

        level_costs.sort(key=lambda x: x.level)

        return OperatorModule(
            module_id=mid,
            name=str(base.get("uniEquipName") or ""),
            icon=str(base.get("uniEquipIcon") or ""),
            desc=str(base.get("uniEquipDesc") or ""),
            type=str(base.get("type") or ""),
            type_icon=str(base.get("typeIcon") or ""),
            type_name1=str(base.get("typeName1") or ""),
            type_name2=base.get("typeName2"),

            show_evolve_phase=str(base.get("showEvolvePhase") or ""),
            unlock_evolve_phase=str(base.get("unlockEvolvePhase") or ""),
            show_level=int(base.get("showLevel", 0) or 0),
            unlock_level=int(base.get("unlockLevel", 0) or 0),

            char_id=str(base.get("charId") or ""),
            char_equip_order=int(base.get("charEquipOrder", 0) or 0),
            has_unlock_mission=bool(base.get("hasUnlockMission")),
            is_special_equip=bool(base.get("isSpecialEquip")),
            char_color=str(base.get("charColor") or ""),

            mission_ids=mids,
            missions=missions,

            unlock_favors=dict(base.get("unlockFavors") or {}),
            level_costs=level_costs,

            battle_detail=dict(battle_detail or {}),
        )