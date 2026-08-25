from __future__ import annotations

import re
from typing import Any

from src.domain.types import QueryResult

ATTRIBUTE_SPECS = [
    ("maxHp", "最大生命值", None),
    ("atk", "攻击力", None),
    ("def", "防御力", None),
    ("magicResistance", "法术抗性", None),
    ("attackSpeed", "攻击速度", None),
    ("baseAttackTime", "攻击间隔", "秒"),
    ("blockCnt", "阻挡数", None),
    ("cost", "部署费用", None),
    ("respawnTime", "再部署时间", "秒"),
]
TRUST_ATTRIBUTE_KEYS = {"maxHp", "atk", "def"}
MASTERY_LEVEL_NAMES = {8: "专精一", 9: "专精二", 10: "专精三"}

# 召唤物/装置属性展示规格（与原版插件 operatorToken 卡片口径一致）
TOKEN_ATTRIBUTE_SPECS = [
    ("maxHp", "最大生命值", None),
    ("atk", "攻击力", None),
    ("def", "防御力", None),
    ("magicResistance", "法术抗性", None),
    ("attackSpeed", "攻击速度", None),
    ("baseAttackTime", "攻击间隔", "秒"),
    ("blockCnt", "阻挡数", None),
    ("cost", "部署费用", None),
    ("respawnTime", "再部署时间", "秒"),
]


def token_max_attr_data(token: Any) -> dict[str, Any]:
    """取召唤物最后一个精英阶段、最后一帧的属性 data（与原版 maxAttrs 口径一致）"""
    if not token.attr:
        return {}
    frames = (token.attr[-1] or {}).get("attr") or []
    if not frames:
        return {}
    return (frames[-1] or {}).get("data") or {}


def token_first_range(token: Any) -> str:
    """取召唤物基础形态的攻击范围文本"""
    if not token.attr:
        return ""
    return str((token.attr[0] or {}).get("range") or "")


def build_token_entries(tokens_map: dict[str, Any], token_ids: list[str]) -> list[dict[str, Any]]:
    """将干员 token_id 列表组装为语义化召唤物条目（过滤不存在的 id）"""
    entries: list[dict[str, Any]] = []
    for token_id in token_ids:
        token = tokens_map.get(token_id)
        if token is None:
            continue

        attr_payload: dict[str, Any] = {}
        max_attr_data = token_max_attr_data(token)
        for raw_key, label, unit in TOKEN_ATTRIBUTE_SPECS:
            value = max_attr_data.get(raw_key)
            if value is None:
                continue
            item: dict[str, Any] = {"精英满级": value}
            if unit:
                item["单位"] = unit
            attr_payload[label] = item

        entries.append(
            {
                "id": token.id,
                "名称": token.name,
                "英文名": token.en_name,
                "职业": token.classes,
                "位置": token.type,
                "描述": token.description,
                "属性": attr_payload,
                "攻击范围": token_first_range(token),
                "天赋": _build_token_talent_payload(token),
                "技能": _build_token_skill_payload(token),
            }
        )
    return entries


def _build_token_talent_payload(token: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in token.talents or []:
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        if not name and not description:
            continue
        result.append(
            {
                "名称": name,
                "描述": description,
            }
        )
    return result


def _build_token_skill_payload(token: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in token.skills or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        entry: dict[str, Any] = {"名称": name}

        sp_type_name = item.get("sp_type_name") or item.get("sp_type") or ""
        if sp_type_name:
            entry["回复方式"] = str(sp_type_name)
        skill_type_name = item.get("skill_type_name") or item.get("skill_type") or ""
        if skill_type_name:
            entry["技能类型"] = str(skill_type_name)

        init_sp = item.get("init_sp") or 0
        sp_cost = item.get("sp_cost") or 0
        if init_sp or sp_cost:
            entry["技力"] = {"初始": init_sp, "消耗": sp_cost}

        duration = item.get("duration") or 0
        if duration and float(duration) > 0:
            entry["持续时间"] = duration

        skill_range = str(item.get("range") or "").strip()
        if skill_range:
            entry["攻击范围"] = skill_range

        description = str(item.get("description") or "").strip()
        if description:
            entry["描述"] = description

        result.append(entry)
    return result


def build_operator_payload(
    result: QueryResult,
    token_entries: list[dict[str, Any]] | None = None,
    token_card_url: str | None = None,
) -> dict[str, Any]:
    data = result.data or {}
    op = data.get("op")
    if op is None:
        return {}

    payload = {
        "名称": {
            "中文名": op.name,
            "英文名": op.en_name,
            "编号": op.number,
            "真名": _build_origin_name_payload(op),
        },
        "分类": {
            "稀有度": {
                "星级": op.rarity,
            },
            "职业": op.classes,
            "分支": op.classes_sub,
            "位置": op.type,
            "攻击范围": op.range,
            "标签": list(op.tags or []),
            "状态标记": {
                "异格干员": bool(op.is_sp),
                "限定干员": bool(op.limit),
                "中坚干员": bool(op.is_classic),
                "可公开招募": bool(op.is_recruit),
                "当前不可获取": bool(op.unavailable),
            },
        },
        "属性": _build_attribute_payload(
            base_attr=data.get("base_attr") or {},
            trust_attr=data.get("trust_attr") or {},
            module_attr=data.get("module_attr") or {},
        ),
        "基础档案": {
            "性别": op.sex,
            "势力": op.nation,
            "阵营": op.group,
            "队伍": op.team,
            "种族": op.race,
            "画师": op.drawer,
            "生日": op.birthday,
            "声优": _build_cv_payload(op.cv),
            "特性": op.operator_trait,
            "简介": op.profile,
            "印象": op.impression,
            "信物": op.potential_item,
            "用途": _dedupe_text(op.operator_usage, op.profile),
            "引述": _dedupe_text(op.operator_quote, op.impression),
            "召唤物": _dedupe_text(op.operator_token, op.potential_item),
            "最高精英等级": op.max_level,
        },
        "潜能提升": _build_potential_payload(data.get("potential_list") or []),
        "天赋": _build_talent_payload(data.get("talents_list") or []),
        "基建技能": _build_building_skill_payload(data.get("building_skills") or []),
        "技能数据说明": _build_basic_skill_data_note(op),
        "技能": _build_skill_payload(
            skills=list(op.skills or []),
            sp_type_name=data.get("sp_type_name") or {},
            skill_type_name=data.get("skill_type_name") or {},
        ),
        # AI-REMOVED 2026-08-13:
        # Reason: 皮肤信息改为由专有 MCP 工具 get_operator_skins 返回，干员详情 JSON 不再携带皮肤列表
        # Trigger: 需求调整——新增 get_operator_skins 接口，从干员详情 JSON 移除皮肤信息
        # Evidence: 用户明确要求“从干员详情json里移除皮肤信息,改为使用专有接口来返回”
        # Replacement: src/app/services/operator_queries.py::query_operator_skins（get_operator_skins 工具）；
        #              条目构建逻辑仍复用本文件 build_skin_payload（原 _build_skin_payload）
        # Risk: Low
        # Human Review: Required
        #
        # Original code:
        #         "皮肤": _build_skin_payload(op),
    }
    if token_entries:
        token_payload: dict[str, Any] = {"列表": token_entries}
        if token_card_url:
            token_payload["卡片"] = token_card_url
        payload["召唤物"] = token_payload
    return _compact_value(payload)


def format_skill_level(level: int) -> str:
    """把解包中的 1~10 级转换为游戏内展示的 1~7 / 专精一~三。"""
    normalized = int(level or 0)
    return MASTERY_LEVEL_NAMES.get(normalized, str(normalized))


def build_operator_skill_payload(
    op: Any,
    sp_type_name: dict[str, str],
    skill_type_name: dict[str, str],
) -> dict[str, Any]:
    """构建一个干员全部技能、全部等级的结构化数据。"""
    skills: list[dict[str, Any]] = []
    for fallback_index, skill in enumerate(getattr(op, "skills", None) or [], start=1):
        levels: list[dict[str, Any]] = []
        for level in getattr(skill, "levels", None) or []:
            unpacked_level = int(getattr(level, "level", 0) or 0)
            mastery = int(getattr(level, "mastery", 0) or 0)
            sp = getattr(level, "sp", None)
            sp_type = getattr(sp, "sp_type", "") if sp else ""
            skill_type = getattr(level, "skill_type", "") or ""

            levels.append(
                {
                    "解包等级": unpacked_level,
                    "游戏内等级": format_skill_level(unpacked_level),
                    "专精等级": mastery,
                    "升级归属": "当前技能独立专精" if mastery else "干员全部技能共用",
                    "回复方式": sp_type_name.get(sp_type, sp_type),
                    "技能类型": skill_type_name.get(skill_type, skill_type),
                    "技力": {
                        "初始": getattr(sp, "init_sp", 0) if sp else 0,
                        "消耗": getattr(sp, "sp_cost", 0) if sp else 0,
                        "最大充能次数": getattr(sp, "max_charge_time", 0) if sp else 0,
                        "回复增量": getattr(sp, "increment", 0) if sp else 0,
                    },
                    "持续时间": getattr(level, "duration", 0) or 0,
                    "持续时间类型": getattr(level, "duration_type", "") or "",
                    "攻击范围": getattr(level, "range", "") or "",
                    "描述": getattr(level, "description", "") or "",
                }
            )

        skill_index = int(getattr(skill, "skill_index", 0) or fallback_index)
        skill_payload: dict[str, Any] = {
            "序号": skill_index,
            "技能ID": getattr(skill, "skill_id", "") or "",
            "名称": getattr(skill, "name", "") or "",
            "图标": getattr(skill, "icon", "") or "",
        }
        if levels:
            skill_payload["最高等级"] = {
                "解包等级": levels[-1]["解包等级"],
                "游戏内等级": levels[-1]["游戏内等级"],
            }
        skill_payload["等级"] = levels
        skills.append(_compact_value(skill_payload))

    payload = {
        "干员": {
            "ID": getattr(op, "id", "") or "",
            "名称": getattr(op, "name", "") or "",
            "英文名": getattr(op, "en_name", "") or "",
            "稀有度": getattr(op, "rarity", 0) or 0,
        },
        "技能等级规则": {
            "等级映射": {
                "解包等级1~7": "游戏内技能等级1~7",
                "解包等级8": "专精一（专一）",
                "解包等级9": "专精二（专二）",
                "解包等级10": "专精三（专三）",
            },
            "普通升级": "1~7级由干员的全部技能共用；未精英化最高4级，精英一后最高7级。",
            "专精升级": "精英二后可以开始专精；每个技能的专精等级分别提升并分别消耗材料。",
            "稀有度限制": "3星干员最高7级；2星及以下干员没有技能。",
        },
        "技能数量": len(skills),
        "技能": skills,
    }
    if not skills:
        payload["说明"] = "该干员没有技能。"
    return payload


def build_skin_payload(op: Any) -> list[dict[str, Any]]:
    """皮肤/立绘条目（仅进入 JSON 结构化输出，不进角色卡模板）。

    AI-CORRECTION 2026-08-13: 原注释“仅进入 JSON 结构化输出”已过时。现由专有接口
    get_operator_skins（query_operator_skins）复用本函数构建皮肤条目并追加
    card_url/立绘URL；干员详情 payload 已移除皮肤区块（见上方 AI-REMOVED）。
    """
    result: list[dict[str, Any]] = []
    for skin in op.skins():
        entry: dict[str, Any] = {
            "id": skin.skin_id,
            "名称": skin.name,
            "立绘键": skin.skin_key,
        }
        if skin.drawer:
            entry["画师"] = skin.drawer
        if skin.group:
            entry["系列"] = skin.group
        if skin.content:
            entry["台词"] = skin.content
        if skin.usage:
            entry["用途"] = skin.usage
        if skin.desc:
            entry["描述"] = skin.desc
        if skin.source:
            entry["获取方式"] = skin.source
        if skin.voice_id:
            entry["语音"] = skin.voice_id
        if skin.voice_type:
            entry["语音类型"] = skin.voice_type
        result.append(entry)
    return result


def render_operator_markdown(
    payload: dict[str, Any],
    image_url: str | None = None,
    image_path: str | None = None,
) -> str:
    if not payload:
        return ""

    name = payload.get("名称") or {}
    category = payload.get("分类") or {}
    archive = payload.get("基础档案") or {}
    attributes = payload.get("属性") or {}
    lines: list[str] = []

    title = name.get("中文名") or "干员"
    lines.append(f"# {title}")
    lines.append("")

    summary_items = [
        ("英文名", name.get("英文名")),
        ("编号", name.get("编号")),
        ("真名", name.get("真名")),
        ("稀有度", _render_star_level(category.get("稀有度"))),
        ("职业", _join_values(category.get("职业"), category.get("分支"), separator=" / ")),
        ("位置", category.get("位置")),
        ("标签", "、".join(category.get("标签") or [])),
        ("势力", archive.get("势力")),
        ("阵营", archive.get("阵营")),
        ("队伍", archive.get("队伍")),
        ("种族", archive.get("种族")),
        ("画师", archive.get("画师")),
        ("生日", archive.get("生日")),
    ]
    status_flags = _render_enabled_flags((category.get("状态标记") or {}))
    if status_flags:
        summary_items.append(("状态标记", status_flags))

    for label, value in summary_items:
        rendered = _render_display_value(value)
        if rendered is not None and rendered != "":
            lines.append(f"- {label}：{rendered}")

    attack_range = category.get("攻击范围")
    if attack_range:
        lines.append("")
        lines.append("## 攻击范围")
        lines.append("")
        lines.append("```text")
        lines.extend(str(attack_range).splitlines())
        lines.append("```")

    if attributes:
        has_module_column = any("模组加成" in item for item in attributes.values())
        lines.append("")
        lines.append("## 属性")
        lines.append("")
        if has_module_column:
            lines.append("| 项目 | 精英满级 | 满信赖加成 | 模组加成 | 最终面板 |")
            lines.append("| --- | ---: | ---: | ---: | ---: |")
            for label, item in attributes.items():
                unit = item.get("单位")
                final_value = item.get("最终面板")
                if final_value is None:
                    final_value = item.get("满信赖面板")
                if final_value is None:
                    final_value = item.get("精英满级")
                lines.append(
                    "| {label} | {base} | {trust} | {module} | {final} |".format(
                        label=label,
                        base=_format_metric(item.get("精英满级"), unit),
                        trust=_format_metric(item.get("满信赖加成"), unit),
                        module=_format_metric(item.get("模组加成"), unit),
                        final=_format_metric(final_value, unit),
                    )
                )
        else:
            lines.append("| 项目 | 精英满级 | 满信赖加成 | 满信赖面板 |")
            lines.append("| --- | ---: | ---: | ---: |")
            for label, item in attributes.items():
                unit = item.get("单位")
                lines.append(
                    "| {label} | {base} | {trust} | {final} |".format(
                        label=label,
                        base=_format_metric(item.get("精英满级"), unit),
                        trust=_format_metric(item.get("满信赖加成"), unit),
                        final=_format_metric(item.get("满信赖面板"), unit),
                    )
                )

    cv_payload = archive.get("声优") or {}
    if cv_payload:
        lines.append("")
        lines.append("## 声优")
        lines.append("")
        for language, names in cv_payload.items():
            lines.append(f"- {language}：{'、'.join(names)}")

    profile = archive.get("简介")
    impression = archive.get("印象")
    trait = archive.get("特性")
    if profile or impression or trait:
        lines.append("")
        lines.append("## 基础档案")
        lines.append("")
        if trait:
            lines.append(f"- 特性：{trait}")
        if profile:
            lines.append(f"- 简介：{profile}")
        if impression:
            lines.append(f"- 印象：{impression}")
        if archive.get("信物"):
            lines.append(f"- 信物：{archive['信物']}")
        if archive.get("最高精英等级"):
            lines.append(f"- 最高精英等级：{archive['最高精英等级']}")

    potentials = payload.get("潜能提升") or []
    if potentials:
        lines.append("")
        lines.append("## 潜能提升")
        lines.append("")
        for item in potentials:
            lines.append(f"1. P{item['潜能阶段']}：{item['效果']}")

    talents = payload.get("天赋") or []
    if talents:
        lines.append("")
        lines.append("## 天赋")
        lines.append("")
        for item in talents:
            lines.append(f"1. {item['名称']}：{item['描述']}")

    building_skills = payload.get("基建技能") or []
    if building_skills:
        lines.append("")
        lines.append("## 基建技能")
        lines.append("")
        for item in building_skills:
            meta = item.get("设施类型")
            prefix = f"{item['解锁阶段']} · {item['名称']}"
            if meta:
                prefix = f"{prefix} · {meta}"
            lines.append(f"1. {prefix}：{item['描述']}")

    skills = payload.get("技能") or []
    if skills:
        lines.append("")
        lines.append("## 技能")
        lines.append("")
        if payload.get("技能数据说明"):
            lines.append(str(payload["技能数据说明"]))
            lines.append("")
        for skill in skills:
            lines.append(f"### S{skill['序号']} {skill['名称']}")
            if skill.get("游戏内等级"):
                lines.append(f"- 数据等级：{skill['游戏内等级']}")
            if skill.get("回复方式"):
                lines.append(f"- 回复方式：{skill['回复方式']}")
            if skill.get("技能类型"):
                lines.append(f"- 技能类型：{skill['技能类型']}")
            if skill.get("技力"):
                sp = skill["技力"]
                lines.append(f"- 技力：{sp.get('初始', 0)}/{sp.get('消耗', 0)}")
            if skill.get("持续时间") is not None:
                lines.append(f"- 持续时间：{_format_plain_number(skill['持续时间'])} 秒")
            if skill.get("描述"):
                lines.append(f"- 描述：{skill['描述']}")
            if skill.get("攻击范围"):
                lines.append("- 攻击范围：")
                lines.append("```text")
                lines.extend(str(skill["攻击范围"]).splitlines())
                lines.append("```")
            lines.append("")
        if lines[-1] == "":
            lines.pop()

    image_refs: list[str] = []
    if image_path:
        image_refs.append(f"本地路径：{image_path}")
    if image_url:
        image_refs.append(f"图片链接：{image_url}")
    if image_refs:
        lines.append("")
        lines.append("## 图片")
        lines.append("")
        for item in image_refs:
            lines.append(f"- {item}")

    return "\n".join(lines).strip()


def _build_attribute_payload(
    base_attr: dict[str, Any],
    trust_attr: dict[str, Any],
    module_attr: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw_key, label, unit in ATTRIBUTE_SPECS:
        base_value = base_attr.get(raw_key)
        if base_value is None:
            continue

        item: dict[str, Any] = {"精英满级": base_value}
        if unit:
            item["单位"] = unit
        trust_value = trust_attr.get(raw_key, 0) if raw_key in TRUST_ATTRIBUTE_KEYS else None
        if raw_key in TRUST_ATTRIBUTE_KEYS:
            item["满信赖加成"] = trust_value
            item["满信赖面板"] = (base_value or 0) + (trust_value or 0)
        module_value = module_attr.get(raw_key, 0)
        if module_value:
            item["模组加成"] = module_value
            item["最终面板"] = (base_value or 0) + (trust_value or 0) + (module_value or 0)
        result[label] = item
    return result


def _build_origin_name_payload(op: Any) -> str | list[str] | None:
    names = [
        str(item).strip()
        for item in (getattr(op, "origin_names", None) or [])
        if str(item).strip() and str(item).strip() != "未知"
    ]
    if len(names) > 1:
        return names
    if names:
        return names[0]

    origin_name = str(getattr(op, "origin_name", "") or "").strip()
    if origin_name and origin_name != "未知":
        return origin_name
    return None


def _build_cv_payload(cv: dict[str, Any] | None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for language, names in (cv or {}).items():
        split_names = _split_names(names)
        if split_names:
            result[str(language)] = split_names
    return result


def _build_potential_payload(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        description = str(item.get("potential_desc") or "").strip()
        if not description:
            continue
        result.append(
            {
                "潜能阶段": int(item.get("potential_rank", 0)) + 1,
                "效果": description,
            }
        )
    return result


def _build_talent_payload(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        name = str(item.get("talents_name") or "").strip()
        description = str(item.get("talents_desc") or "").strip()
        if not name and not description:
            continue
        result.append(
            {
                "名称": name,
                "描述": description,
            }
        )
    return result


def _build_building_skill_payload(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        name = str(item.get("bs_name") or "").strip()
        description = str(item.get("bs_desc") or "").strip()
        if not name and not description:
            continue
        result.append(
            {
                "解锁阶段": f"精英{int(item.get('bs_unlocked', 0) or 0)}",
                "名称": name,
                "描述": description,
                "设施类型": str(item.get("bs_room_type") or "").strip(),
            }
        )
    return result


def _build_skill_payload(
    skills: list[Any],
    sp_type_name: dict[str, str],
    skill_type_name: dict[str, str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, skill in enumerate(skills, start=1):
        if not getattr(skill, "levels", None):
            continue
        last = skill.levels[-1]
        sp = getattr(last, "sp", None)
        result.append(
            {
                "序号": index,
                "名称": getattr(skill, "name", "") or "",
                "技能等级": getattr(last, "level", None),
                "游戏内等级": format_skill_level(getattr(last, "level", 0)),
                "回复方式": sp_type_name.get(getattr(sp, "sp_type", ""), getattr(sp, "sp_type", "") or ""),
                "技能类型": skill_type_name.get(
                    getattr(last, "skill_type", ""),
                    getattr(last, "skill_type", "") or "",
                ),
                "技力": {
                    "初始": getattr(sp, "init_sp", 0) if sp else 0,
                    "消耗": getattr(sp, "sp_cost", 0) if sp else 0,
                },
                "持续时间": getattr(last, "duration", None),
                "攻击范围": getattr(last, "range", "") or "",
                "描述": getattr(last, "description", "") or "",
            }
        )
    return result


def _build_basic_skill_data_note(op: Any) -> str:
    skills = [skill for skill in (getattr(op, "skills", None) or []) if getattr(skill, "levels", None)]
    if not skills:
        return "该干员没有技能。"

    max_levels = [int(skill.levels[-1].level) for skill in skills]
    if all(level == 10 for level in max_levels):
        return "以下每个技能均展示专精三数据；完整技能列表和全部等级数据请查询 get_operator_skill。"
    if getattr(op, "rarity", 0) == 3 and all(level == 7 for level in max_levels):
        return "该干员为3星干员，以下每个技能均展示7级数据；完整技能列表和全部等级数据请查询 get_operator_skill。"
    return "以下每个技能均展示该技能最高可用等级的数据，具体等级见游戏内等级；完整技能列表和全部等级数据请查询 get_operator_skill。"


def _split_names(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return [item.strip() for item in re.split(r"[，,、/]+", str(value)) if item.strip()]


def _compact_value(value: Any) -> Any:
    if isinstance(value, dict):
        compacted = {}
        for key, item in value.items():
            reduced = _compact_value(item)
            if reduced is None:
                continue
            if isinstance(reduced, (dict, list)) and not reduced:
                continue
            compacted[key] = reduced
        return compacted
    if isinstance(value, list):
        compacted = []
        for item in value:
            reduced = _compact_value(item)
            if reduced is None:
                continue
            if isinstance(reduced, (dict, list)) and not reduced:
                continue
            compacted.append(reduced)
        return compacted
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def _render_star_level(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    star = payload.get("星级")
    if star is None:
        return None
    return f"{star} 星"


def _render_enabled_flags(flags: dict[str, Any]) -> str | None:
    enabled = [name for name, value in flags.items() if value]
    if not enabled:
        return None
    return "、".join(enabled)


def _join_values(*values: Any, separator: str = " ") -> str | None:
    items = [str(value).strip() for value in values if value is not None and str(value).strip()]
    if not items:
        return None
    return separator.join(items)


def _render_display_value(value: Any) -> str | None:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if not items:
            return None
        return "、".join(items)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe_text(value: Any, baseline: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    base_text = str(baseline).strip() if baseline is not None else ""
    if not text or text == base_text:
        return None
    return text


def _format_metric(value: Any, unit: str | None) -> str:
    if value is None:
        return "-"
    rendered = _format_plain_number(value)
    if unit:
        return f"{rendered} {unit}"
    return rendered


def _format_plain_number(value: Any) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)
