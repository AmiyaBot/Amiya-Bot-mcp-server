"""基于本地解包数据构建材料详情卡片。"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from src.app.context import AppContext, get_bundle_resource_root
from src.domain.services.operator import build_operator_template_font_url
from src.domain.types import QueryResult


MATERIAL_ASSET_PATH = Path("assets") / "item"


def _image_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    suffix = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".webp": "image/webp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix)
    if not mime:
        return None
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime};base64,{encoded}"


def _collect_icon_ids(value: Any, output: set[str]) -> None:
    if isinstance(value, dict):
        icon_id = str(value.get("icon_id") or "").strip()
        if icon_id:
            output.add(icon_id)
        for child in value.values():
            _collect_icon_ids(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_icon_ids(child, output)


def _build_icon_data(icon_ids: set[str], resource_root: Path) -> dict[str, str]:
    asset_root = resource_root / MATERIAL_ASSET_PATH
    result: dict[str, str] = {}
    for icon_id in sorted(icon_ids):
        path = asset_root / icon_id
        if not path.suffix:
            path = path.with_suffix(".png")
        data_uri = _image_data_uri(path)
        if data_uri:
            result[icon_id] = data_uri
    return result


def build_material_query_result(ctx: AppContext, material_id: str) -> QueryResult | None:
    """从当前 DataBundle 构建材料卡片所需数据，不访问外部服务。"""
    bundle = ctx.data_repository.get_bundle()
    material = bundle.materials.get(material_id)
    if not isinstance(material, dict):
        return None

    icon_ids: set[str] = set()
    _collect_icon_ids(material, icon_ids)
    return QueryResult(
        type="material",
        key=str(material.get("name") or material_id),
        title=str(material.get("name") or material_id),
        data={
            "material": material,
            "icon_data": _build_icon_data(icon_ids, get_bundle_resource_root(bundle, ctx)),
            "template_font_url": build_operator_template_font_url(ctx.cfg.ProjectRoot),
        },
    )
