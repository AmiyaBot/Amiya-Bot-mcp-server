from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any
import base64

from src.app.context import AppContext
from src.domain.types import QueryResult
from src.helpers.card_urls import build_card_url

RECRUIT_CARD_REVISION = "recruit-v2"


def _image_data_uri(path: Path | None) -> str:
    if path is None or not path.is_file() or path.is_symlink():
        return ""
    try:
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""


def _find_combinations(tags: list[str]) -> list[list[str]]:
    result: list[list[str]] = []
    for size in range(1, min(3, len(tags)) + 1):
        for combo in combinations(tags, size):
            values = list(combo)
            if not ("高级资深干员" in values and "资深干员" in values):
                result.append(values)
    result.reverse()
    return result


def _normalize_tags(text: str, known_tags: set[str]) -> tuple[list[str], int]:
    """匹配数据标签，并兼容源插件定义的三个公招简称。"""
    # 这些简称来自源插件的输入处理，不是额外的游戏词条；实际查询标签
    # 仍必须存在于当前 gacha/character 数据中。
    aliases = {
        "高资": "高级资深干员",
        "高级资深": "高级资深干员",
        "资深": "资深干员",
    }
    cleaned = text.replace("公开招募", "").replace("公招", "")
    candidates = sorted(
        ((alias, target) for alias, target in aliases.items() if target in known_tags),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    candidates.extend((tag, tag) for tag in sorted(known_tags, key=len, reverse=True))

    found: list[tuple[int, str]] = []
    remaining = cleaned
    for source, target in candidates:
        start = remaining.find(source)
        if start >= 0:
            found.append((cleaned.find(source), target))
            remaining = remaining.replace(source, " ")
    tags_list: list[str] = []
    for _, tag in sorted(found, key=lambda item: item[0]):
        if tag not in tags_list:
            tags_list.append(tag)
    if not tags_list:
        return [], 5
    return tags_list, 6 if "高级资深干员" in tags_list else 5


async def query_recruit(context: AppContext, text: str) -> dict[str, Any]:
    bundle = context.data_repository.get_bundle()
    recruit_operators = [op for op in (bundle.operators or {}).values() if op.is_recruit]
    known_tags = {tag for op in recruit_operators for tag in op.tags}
    tags, max_rarity = _normalize_tags(text or "", known_tags)
    if not tags:
        return {"message": "未识别到有效的公招标签", "tags": [], "available_tags": sorted(known_tags)}

    operators: dict[str, dict[str, Any]] = {}
    for operator in (bundle.operators or {}).values():
        if not operator.is_recruit or operator.rarity > max_rarity:
            continue
        matched = [tag for tag in operator.tags if tag in tags]
        if matched:
            operators[operator.name] = {
                "operator_id": operator.id,
                "operator_name": operator.name,
                "operator_rarity": operator.rarity,
                "operator_tags": matched,
            }

    groups: list[dict[str, Any]] = []
    for combo in [tags] if len(tags) == 1 else _find_combinations(tags):
        candidates = []
        for item in operators.values():
            if not all(tag in item["operator_tags"] for tag in combo):
                continue
            if item["operator_rarity"] == 6 and "高级资深干员" not in combo:
                continue
            if item["operator_rarity"] >= 4 or item["operator_rarity"] == 1:
                candidates.append(item)
        if candidates:
            groups.append({
                "tags": combo,
                "max_rarity": max(item["operator_rarity"] for item in candidates),
                "operators": sorted(candidates, key=lambda item: (-item["operator_rarity"], item["operator_name"])),
            })

    if not groups:
        return {"message": "没有找到可以锁定稀有干员的组合", "tags": tags}
    groups.sort(key=lambda item: (-len(item["tags"]), -item["max_rarity"]))

    # 使用与源插件一致的深色横向布局，复用现有卡片服务输出图片 URL。
    resource_root = Path(context.cfg.ResourcePath)
    for group in groups:
        for item in group["operators"]:
            portrait = resource_root / "assets" / "portrait" / f'{item["operator_id"]}#1.png'
            item["image_data"] = _image_data_uri(portrait)
    bundle_version = str(getattr(bundle, "version", None) or "v0")
    payload_key = f"recruit:{'|'.join(tags)}:{bundle_version}:{RECRUIT_CARD_REVISION}"
    card_payload = QueryResult(
        type="recruit",
        key=payload_key,
        title="公开招募",
        data={
            "groups": groups,
            "tags": tags,
            "template_font_url": None,
        },
    )
    try:
        awaitable = context.card_service.get(
            template="recruit",
            payload_key=payload_key,
            payload=card_payload,
            params={
                "viewport": {"width": 1280, "height": 720, "deviceScaleFactor": 1},
                "full_page": True,
                "wait_until": "networkidle",
            },
            format="png",
        )
        await awaitable
        card_url = build_card_url(
            cfg=context.cfg,
            template="recruit",
            payload_key=payload_key,
            format="png",
        )
    except Exception:
        card_url = None

    response = {"tags": tags, "groups": groups}
    if card_url:
        response["card_image_url"] = card_url
    return response
