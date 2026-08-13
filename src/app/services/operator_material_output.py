# app/services/operator_material_output.py
"""材料页面的语义化结果契约：结构化 payload 与 Markdown 渲染。

对齐 STAGE2-RQ-002 风格：中文键、嵌套结构、compact 清洗空值。
结构化 payload 不携带图片 URL，「图标」字段存 iconId 语义标识。
"""
from __future__ import annotations

from typing import Any

from src.app.services.operator_output import _compact_value
from src.domain.types import QueryResult


def build_operator_material_payload(result: QueryResult) -> dict[str, Any]:
    data = result.data or {}
    op = data.get("op")
    if op is None:
        return {}

    evolve_groups = data.get("evolve_groups") or []
    common_levels = data.get("common_levels") or []
    mastery_groups = data.get("mastery_groups") or []

    mastery_payload: list[dict[str, Any]] = []
    for group in mastery_groups:
        item = {
            "技能名": group.get("技能名"),
        }
        for mastery_name in ("专精一", "专精二", "专精三"):
            materials = group.get(mastery_name)
            if materials:
                item[mastery_name] = [
                    {"名称": m.get("名称"), "数量": m.get("数量"), "图标": m.get("图标")}
                    for m in materials
                ]
        mastery_payload.append(item)

    skill_upgrade_payload: dict[str, Any] = {
        "通用升级": [
            {
                "等级": level.get("等级"),
                "材料": [
                    {"名称": m.get("名称"), "数量": m.get("数量"), "图标": m.get("图标")}
                    for m in (level.get("材料") or [])
                ],
            }
            for level in common_levels
        ],
        "专精": mastery_payload,
    }

    payload = {
        "名称": {
            "干员id": getattr(op, "id", ""),
            "中文名": getattr(op, "name", ""),
            "英文名": getattr(op, "en_name", ""),
            "星级": getattr(op, "rarity", None),
        },
        "精英化材料": [
            {
                "阶段": group.get("阶段"),
                "材料": [
                    {"名称": m.get("名称"), "数量": m.get("数量"), "图标": m.get("图标")}
                    for m in (group.get("材料") or [])
                ],
            }
            for group in evolve_groups
        ],
        "技能升级材料": skill_upgrade_payload,
    }
    return _compact_value(payload)


def _render_material_list(items: list[dict[str, Any]]) -> str:
    parts = [f"{item.get('名称')} ×{item.get('数量')}" for item in items if item.get("名称")]
    return "、".join(parts) if parts else "无"


def render_operator_material_markdown(
    payload: dict[str, Any],
    image_url: str | None = None,
    image_path: str | None = None,
) -> str:
    if not payload:
        return ""

    name = (payload.get("名称") or {}).get("中文名") or "干员"
    lines: list[str] = [f"# {name} 材料", ""]

    evolve_groups = payload.get("精英化材料") or []
    if evolve_groups:
        lines.append("## 精英化")
        lines.append("")
        for group in evolve_groups:
            lines.append(f"### {group.get('阶段')}")
            lines.append("")
            lines.append(f"- {_render_material_list(group.get('材料') or [])}")
            lines.append("")

    skill_upgrade = payload.get("技能升级材料") or {}
    common_levels = skill_upgrade.get("通用升级") or []
    mastery_groups = skill_upgrade.get("专精") or []
    if common_levels or mastery_groups:
        lines.append("## 技能升级")
        lines.append("")
        if common_levels:
            lines.append("### 通用升级")
            lines.append("")
            for level in common_levels:
                lines.append(f"- Lv{level.get('等级')}：{_render_material_list(level.get('材料') or [])}")
            lines.append("")
        if mastery_groups:
            lines.append("### 专精")
            lines.append("")
            for group in mastery_groups:
                lines.append(f"#### {group.get('技能名')}")
                lines.append("")
                for mastery_name in ("专精一", "专精二", "专精三"):
                    materials = group.get(mastery_name)
                    if materials:
                        lines.append(f"- {mastery_name}：{_render_material_list(materials)}")
                lines.append("")

    image_refs: list[str] = []
    if image_path:
        image_refs.append(f"本地路径：{image_path}")
    if image_url:
        image_refs.append(f"图片链接：{image_url}")
    if image_refs:
        lines.append("## 图片")
        lines.append("")
        for item in image_refs:
            lines.append(f"- {item}")

    return "\n".join(lines).strip()
