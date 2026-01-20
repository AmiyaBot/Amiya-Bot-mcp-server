# src/data/models/_operator_impl.py
from typing import Dict, Any, List
from src.domain.models.operator import Operator,OperatorPhase, Skill, SkillLevel, SkillSpData, OperatorModule, STR_DICT, LIST_STR_DICT
from src.domain.models.generic import Cost, MaterialCost, parse_cost
from src.helpers.bundle import *

class OperatorImpl(Operator):
    def __init__(
        self,
        op_id: str,
        data: dict,
        tables: Dict[str, Any],
        is_recruit: bool = False,
    ):
        super().__init__()

        sub_classes = get_table(tables, "uniequip_table", source="gamedata", default={}).get("subProfDict", {})
        character_table = get_table(tables, "character_table", source="gamedata", default={})
        team_table = get_table(tables, "handbook_team_table", source="gamedata", default={})
        items = get_table(tables, "item_table", source="gamedata", default={}).get("items", {})

        data["name"] = (data.get("name") or "").strip()

        self.id = op_id

        # type / rarity / number
        pos = data.get("position")
        self.type = get_table(tables, "types", source="local", default={}).get(pos, "未知")

        rarity_raw = data.get("rarity", 0)
        if isinstance(rarity_raw, str):
            # "TIER_5" 之类
            try:
                self.rarity = int(rarity_raw.split("_")[-1])
            except Exception:
                self.rarity = 0
        else:
            # 有些表是 0-based
            self.rarity = int(rarity_raw) + 1 if isinstance(rarity_raw, int) else 0

        self.number = str(data.get("displayNumber") or "")

        # name / en_name
        self.name = data.get("name") or ""
        self.en_name = data.get("appellation") or ""
        self.wiki_name = self.name
        self.index_name = remove_punctuation(self.name)
        self.origin_name = "未知"

        # classes
        prof = data.get("profession")
        self.classes_code = prof or ""
        self.classes = get_table(tables, "classes", source="local", default={}).get(prof, "未知")

        sub_prof_id = data.get("subProfessionId")
        self.classes_sub = sub_classes.get(sub_prof_id, {}).get("subProfessionName", "未知")

        # faction/team/group/nation
        self.team_id = str(data.get("teamId") or "")
        self.team = team_table.get(self.team_id, {}).get("powerName", "未知") if self.team_id else "未知"

        self.group_id = str(data.get("groupId") or "")
        self.group = team_table.get(self.group_id, {}).get("powerName", "未知") if self.group_id else "未知"

        nation_id = character_table.get(op_id, {}).get("nationId")
        self.nation_id = str(nation_id or "")
        self.nation = team_table.get(self.nation_id, {}).get("powerName", "未知") if self.nation_id else "未知"

        # profile / impression
        self.profile = data.get("itemUsage") or "无"
        self.impression = data.get("itemDesc") or "无"

        # potential_item
        self.potential_item = ""
        pid = data.get("potentialItemId")
        if pid and pid in items:
            self.potential_item = items[pid].get("description", "")

        # flags
        self.limit = self.name in get_table(tables, "limit", source="amiyabot", default=[])
        self.unavailable = self.name in get_table(tables, "unavailable", source="amiyabot", default=[])

        self.is_recruit = is_recruit
        self.is_classic = bool(data.get("classicPotentialItemId"))
        self.is_sp = bool(data.get("isSpChar"))

        self._init_phases(data)
        self._init_tags(data, tables)
        self._init_range(data, tables)
        self.cv = {}
        self._init_cv(tables)
        self._init_origin(character_table, data, tables)
        self._init_detail(data, tables)
        self._init_talents(data, tables)
        self._init_skills(data, tables)
        self._init_modules(tables)   # <- 新增这一行（放 skills 后面就行）

    def _init_phases(self, data):
        raw = data.get("phases") or []
        self.phases = [OperatorPhase.from_gamedata(i, p) for i, p in enumerate(raw)]

    def _init_tags(self, data, tables):
        tags = [self.classes, self.type]
        hs = get_table(tables, "rarity_tags", source="local", default={})
        if str(self.rarity) in hs:
            tags.append(hs[str(self.rarity)])
        self.tags = (data.get("tagList") or []) + tags

    def _init_range(self, data, tables):
        range_table = get_table(tables, "range_table", source="gamedata", default={})

        if not self.phases:
            self.range = "无范围"
            return

        range_id = self.phases[-1].range_id
        grids = range_table.get(range_id, {}).get("grids")
        self.range = build_range(grids) if grids else "无范围"


    def _init_cv(self, tables):
        word_data = get_table(tables, "charword_table", source="gamedata", default={})
        # 按旧逻辑读取 voiceLangDict
        vdict = (word_data.get("voiceLangDict") or {}).get(self.id, {}).get("dict", {})
        vtype = word_data.get("voiceLangTypeDict") or {}
        if vdict and vtype:
            self.cv = {vtype.get(k, {}).get("name", k): v.get("cvName", "") for k, v in vdict.items()}

    def _init_origin(self, character_table: dict, data, tables):
        sp_char_groups = get_table(tables, "char_meta_table", source="local", default={}).get("spCharGroups") or {}
        for oid, group in sp_char_groups.items():
            if self.id in (group or []):
                self.origin_name = character_table.get(oid, {}).get("name", "未知")
                return

    # ------------------ domain 接口实现（先做可用版，复杂聚合可逐步补齐） ------------------

    def _init_detail(self, data, tables):
        items = get_table(tables, "item_table", source="gamedata", default={}).get("items", {})
        token = items.get("p_" + self.id)

        # max_level
        self.max_level = ""
        if self.phases:
            last = self.phases[-1]
            self.max_level = f"{last.phase_index} - {last.max_level}"

        trait = html_tag_format(data.get("description") or "")
        # 你 trait 解析逻辑不变...
        self.operator_trait = (trait or "").replace("\\n", "\n")
        self.operator_usage = data.get("itemUsage") or ""
        self.operator_quote = data.get("itemDesc") or ""
        self.operator_token = token.get("description", "") if token else ""

    def _init_talents(self, data, tables):
        talents = []
        for item in data.get("talents") or []:
            cand = item.get("candidates") or []
            if cand:
                max_item = cand[-1]
                talents.append({"talents_name": max_item.get("name", ""), "talents_desc": html_tag_format(max_item.get("description", ""))})
        self._talents = talents

    def talents(self) -> LIST_STR_DICT:
        return self._talents

    def _init_skills(self, data: dict, tables: dict):
        skill_table = get_table(tables, "skill_table", source="gamedata", default={})
        range_table = get_table(tables, "range_table", source="gamedata", default={})

        # Lv2..Lv7 通用升级材料：level -> costs
        common_cost_by_level: dict[int, list[Cost]] = {}
        for idx, item in enumerate(data.get("allSkillLvlup") or []):
            level = idx + 2  # 2..7
            costs = [
                parse_cost(c)
                for c in (item.get("lvlUpCost") or [])
            ]
            common_cost_by_level[level] = costs

        skills: list[Skill] = []

        for sidx, sk in enumerate(data.get("skills") or []):
            sid = sk.get("skillId")
            if not sid or sid not in skill_table:
                continue

            detail = skill_table[sid] or {}
            raw_levels = detail.get("levels") or []
            if not raw_levels:
                continue

            icon = detail.get("iconId") or detail.get("skillId") or sid

            # 专精材料：index 0..2 -> level 8..10
            spec_cost_by_level: dict[int, list[Cost]] = {}
            spec_data = sk.get("specializeLevelUpData") or sk.get("levelUpCostCond") or []
            for i, cond in enumerate(spec_data):
                level = 8 + i  # 8..10
                spec_cost_by_level[level] = [
                    parse_cost(c)
                    for c in (cond.get("levelUpCost") or [])
                ]

            levels: list[SkillLevel] = []

            for i, lev in enumerate(raw_levels):
                level_no = i + 1  # 1..10（包含专精）
                mastery = 0
                if level_no >= 8:
                    mastery = level_no - 7  # 8->1, 9->2, 10->3

                # desc 模板替换 + 格式化
                bb = lev.get("blackboard") or []
                raw_desc = lev.get("description") or ""
                desc = parse_template(bb, raw_desc) if raw_desc else raw_desc
                desc = html_tag_format(desc).replace("\\n", "\n")

                # range：优先技能rangeId，否则 fallback 干员自身 range
                skill_range = self.range
                rid = lev.get("rangeId")
                if rid and rid in range_table:
                    grids = range_table[rid].get("grids")
                    if grids:
                        skill_range = build_range(grids)

                spd = lev.get("spData") or {}
                sp = SkillSpData(
                    sp_type=str(spd.get("spType") or ""),
                    init_sp=int(spd.get("initSp") or 0),
                    sp_cost=int(spd.get("spCost") or 0),
                    max_charge_time=int(spd.get("maxChargeTime") or 0),
                    increment=float(spd.get("increment") or 0.0),
                )

                # costs：按等级贴
                costs: list[Cost] = []
                if 2 <= level_no <= 7:
                    costs = common_cost_by_level.get(level_no, [])
                elif 8 <= level_no <= 10:
                    costs = spec_cost_by_level.get(level_no, [])

                levels.append(
                    SkillLevel(
                        level=level_no,
                        mastery=mastery,
                        name=str(lev.get("name") or ""),
                        skill_type=str(lev.get("skillType") or ""),
                        duration=float(lev.get("duration") or 0.0),
                        duration_type=str(lev.get("durationType") or ""),
                        range=skill_range,
                        description=desc,
                        sp=sp,
                        costs=costs,
                    )
                )

            skills.append(
                Skill(
                    skill_id=sid,
                    skill_index=sidx + 1,
                    icon=str(icon),
                    name=str(raw_levels[0].get("name") or ""),
                    levels=levels,
                )
            )

        self.skills = skills

    def _init_modules(self, tables: Dict[str, Any]):
        uniequip = get_table(tables, "uniequip_table", source="gamedata", default={})
        battle = get_table(tables, "battle_equip_table", source="gamedata", default={})

        equip_dict = (uniequip.get("equipDict") or {}) if isinstance(uniequip, dict) else {}
        char_equip = (uniequip.get("charEquip") or {}) if isinstance(uniequip, dict) else {}
        mission_dict = (uniequip.get("missionList") or {}) if isinstance(uniequip, dict) else {}

        # 这个表有时会长这样：battle["uniequip_002_mgllan"] = {"phases":[...]}
        battle_dict = battle if isinstance(battle, dict) else {}

        module_ids = char_equip.get(self.id) or []
        modules: list[OperatorModule] = []

        for mid in module_ids:
            base = equip_dict.get(mid)
            if not base:
                continue

            # 重要：不要改 base（它来自全局表），直接喂给 from_gamedata（内部会 dict(...)）
            m = OperatorModule.from_gamedata(
                base=base,
                battle_detail=battle_dict.get(mid) or {},
                mission_dict=mission_dict,
            )
            modules.append(m)

        # 可选：按 charEquipOrder 排序，保证稳定输出
        modules.sort(key=lambda x: x.char_equip_order)

        self.modules = modules

    def skins(self) -> LIST_STR_DICT:
        # 旧项目 skins() 依赖 Collection 皮肤列表；你可以把 skins 表在 load_bundle 阶段预处理塞进 tables，再在这里生成
        return []

    def voices(self) -> LIST_STR_DICT:
        return []
