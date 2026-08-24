"""干员模组的结构化响应与 Markdown 输出。"""
from __future__ import annotations

from typing import Any

from src.app.services.operator_output import _compact_value
from src.domain.types import QueryResult


def _build_attribute_payload(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "属性": item.get("name"),
            "数值": item.get("value"),
            "原始键": item.get("key"),
        }
        for item in items
    ]


def _build_effect_payload(items: list[dict[str, Any]], *, talent: bool = False) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        entry = {
            "作用目标": item.get("target"),
            "描述": item.get("description"),
            "潜能要求": item.get("potential_rank"),
        }
        if talent:
            entry["名称"] = item.get("name")
        result.append(entry)
    return result


def _build_token_attribute_payload(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "召唤物id": item.get("token_id"),
            "召唤物名称": item.get("token_name"),
            "属性提升": _build_attribute_payload(item.get("attributes") or []),
        }
        for item in items
    ]


def build_operator_module_payload(result: QueryResult) -> dict[str, Any]:
    data = result.data or {}
    op = data.get("op")
    if op is None:
        return {}

    modules: list[dict[str, Any]] = []
    for module in data.get("modules") or []:
        unlock = module.get("unlock_condition") or {}
        levels = []
        for phase in module.get("phases") or []:
            levels.append(
                {
                    "等级": phase.get("level"),
                    "信赖要求": phase.get("favor_percent"),
                    "属性提升": _build_attribute_payload(phase.get("attributes") or []),
                    "召唤物属性提升": _build_token_attribute_payload(
                        phase.get("token_attributes") or []
                    ),
                    "分支特性更新": _build_effect_payload(phase.get("trait_updates") or []),
                    "天赋更新": _build_effect_payload(
                        phase.get("talent_updates") or [],
                        talent=True,
                    ),
                    "升级材料": [
                        {
                            "名称": item.get("名称"),
                            "数量": item.get("数量"),
                            "图标": item.get("图标"),
                        }
                        for item in (phase.get("materials") or [])
                    ],
                }
            )

        modules.append(
            {
                "id": module.get("id"),
                "名称": module.get("name"),
                "类型": {
                    "类别": module.get("type_name"),
                    "代码": module.get("type_code"),
                    "原始类型": module.get("type"),
                },
                "图标URL": module.get("module_icon_url"),
                "类型图标URL": module.get("type_icon_url"),
                "描述": module.get("description"),
                "展示条件": {
                    "精英阶段": (module.get("show_condition") or {}).get("phase"),
                    "等级": (module.get("show_condition") or {}).get("level"),
                },
                "解锁条件": {
                    "精英阶段": unlock.get("phase"),
                    "等级": unlock.get("level"),
                    "信赖": unlock.get("favor"),
                    "任务": [
                        {"id": item.get("id"), "描述": item.get("description")}
                        for item in (unlock.get("missions") or [])
                    ],
                },
                "等级数据": levels,
            }
        )

    return _compact_value(
        {
            "干员": {
                "id": getattr(op, "id", ""),
                "中文名": getattr(op, "name", ""),
                "英文名": getattr(op, "en_name", ""),
            },
            "模组": modules,
        }
    )


def _format_materials(items: list[dict[str, Any]]) -> str:
    return "、".join(
        f"{item.get('名称')} ×{item.get('数量')}"
        for item in items
        if item.get("名称")
    ) or "无"


def render_operator_module_markdown(
    payload: dict[str, Any],
    image_url: str | None = None,
    image_path: str | None = None,
) -> str:
    if not payload:
        return ""

    operator = payload.get("干员") or {}
    lines: list[str] = [f"# {operator.get('中文名') or '干员'} 模组"]
    for module in payload.get("模组") or []:
        type_data = module.get("类型") or {}
        type_code = type_data.get("代码")
        type_suffix = f" · {type_code}" if type_code else ""
        lines.extend(["", f"## {module.get('名称')}{type_suffix}", ""])

        levels = module.get("等级数据") or []
        if not levels:
            if module.get("描述"):
                lines.append(str(module["描述"]))
            continue

        unlock = module.get("解锁条件") or {}
        unlock_parts = [
            str(unlock.get("精英阶段") or ""),
            f"Lv.{unlock.get('等级')}" if unlock.get("等级") is not None else "",
            f"信赖 {unlock.get('信赖')}%" if unlock.get("信赖") else "",
        ]
        lines.append(f"- 解锁条件：{' · '.join(item for item in unlock_parts if item)}")
        for mission in unlock.get("任务") or []:
            lines.append(f"- 解锁任务：{mission.get('描述')}")

        for level in levels:
            lines.extend(["", f"### Lv.{level.get('等级')}", ""])
            if level.get("信赖要求"):
                lines.append(f"- 升级要求：信赖 {level.get('信赖要求')}%")
            attributes = level.get("属性提升") or []
            if attributes:
                attr_text = "、".join(
                    f"{item.get('属性')} {float(item.get('数值') or 0):+g}"
                    for item in attributes
                )
                lines.append(f"- 属性提升：{attr_text}")
            for item in level.get("分支特性更新") or []:
                lines.append(f"- 分支特性：{item.get('描述')}")
            for item in level.get("天赋更新") or []:
                name = f"{item.get('名称')}：" if item.get("名称") else ""
                lines.append(f"- 天赋更新：{name}{item.get('描述')}")
            materials = level.get("升级材料") or []
            if materials:
                lines.append(f"- 升级材料：{_format_materials(materials)}")

    image_refs = []
    if image_path:
        image_refs.append(f"本地路径：{image_path}")
    if image_url:
        image_refs.append(f"图片链接：{image_url}")
    if image_refs:
        lines.extend(["", "## 图片", ""])
        lines.extend(f"- {item}" for item in image_refs)

    return "\n".join(lines).strip()
