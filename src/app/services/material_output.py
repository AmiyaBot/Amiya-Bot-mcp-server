"""材料详情的结构化输出。"""
from __future__ import annotations

from typing import Any

from src.domain.types import QueryResult


def build_material_payload(result: QueryResult) -> dict[str, Any]:
    material = result.data.get("material") if result.data else None
    return material if isinstance(material, dict) else {}
