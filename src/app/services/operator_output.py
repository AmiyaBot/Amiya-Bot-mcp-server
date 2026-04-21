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


def build_operator_payload(result: QueryResult) -> dict[str, Any]:
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
        "技能": _build_skill_payload(
            skills=list(op.skills or []),
            sp_type_name=data.get("sp_type_name") or {},
            skill_type_name=data.get("skill_type_name") or {},
        ),
    }
    return _compact_value(payload)


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
        for skill in skills:
            lines.append(f"### S{skill['序号']} {skill['名称']}")
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