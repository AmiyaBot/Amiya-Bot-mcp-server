from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.app.card_service import CardArtifact
from src.app.renderers.jinja_html_renderer import JinjaHtmlRenderer
from src.app.renderers.jinja_template_loader import JinjaTemplateLoader
from src.app.services.integrated_strategy_collectible_assets import (
    IntegratedStrategyCollectibleIconArtifact,
)
from src.app.services.operator_queries import QueryExecutionResult
from src.app.services.search_card import build_search_selection_query_result
from src.app.services.search_card_cache import (
    SearchCardCache,
    build_search_result_cache_key,
)
from src.app.services import search_queries


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PNG_BYTES = b"\x89PNG\r\n\x1a\nsearch-card-test"


def _write_asset(root: Path, relative: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_BYTES)
    return path


def _card_context(tmp_path: Path):
    _write_asset(tmp_path, "assets/portrait/char_test#1.png")
    _write_asset(tmp_path, "assets/portrait/char_test@skin#1.png")
    _write_asset(tmp_path, "assets/avatar/token_test#1.png")
    _write_asset(tmp_path, "assets/enemy/enemy_test.png")
    _write_asset(tmp_path, "assets/map/stage_test.png")
    _write_asset(tmp_path, "assets/item/material_icon.png")
    collectible_icon = _write_asset(
        tmp_path,
        "cache/integrated_strategy_collectible_icons/relic_icon.png",
    )

    bundle = SimpleNamespace(
        version="search-card-test",
        operators={
            "char_test": SimpleNamespace(classes="术师", rarity=6),
        },
        materials={
            "material_test": {"icon_id": "material_icon", "rarity": 4},
        },
    )
    cfg = SimpleNamespace(
        ProjectRoot=PROJECT_ROOT,
        ResourcePath=tmp_path,
        BaseUrl="https://example.test/",
        SearchCardCacheMaxEntries=128,
        SearchCardCacheMaxBytes=256 * 1024 * 1024,
        SearchCardCacheMaxEntryBytes=16 * 1024 * 1024,
    )
    context = SimpleNamespace(
        cfg=cfg,
        data_repository=SimpleNamespace(get_bundle=lambda: bundle),
    )
    artifact = IntegratedStrategyCollectibleIconArtifact(
        icon_id="relic_icon",
        path=collectible_icon,
        url="https://example.test/icons/relic_icon.png",
    )
    return context, artifact


def test_search_selection_card_uses_type_specific_assets_and_global_indexes(
    tmp_path: Path,
) -> None:
    context, collectible_artifact = _card_context(tmp_path)
    items = [
        {"id": "char_test", "name": "测试干员", "type": "干员"},
        {
            "id": "enemy_test",
            "name": "测试敌人",
            "type": "敌人",
            "enemy_index": "X1",
            "enemy_level": "精英",
        },
        {
            "id": "stage_test",
            "name": "测试关卡",
            "type": "关卡",
            "code": "T-1",
            "difficulty": "普通",
            "stage_type": "活动",
        },
        {
            "id": "char_test@skin#1",
            "name": "测试皮肤",
            "type": "皮肤",
            "operator_name": "测试干员",
        },
        {
            "id": "token_test",
            "name": "测试召唤物",
            "type": "召唤物",
            "operator_name": "测试干员",
        },
        {
            "id": "material_test",
            "name": "测试材料",
            "type": "材料",
        },
        {
            "id": "relic_test",
            "name": "测试藏品",
            "type": "集成战略藏品",
            "topic_name": "测试主题",
            "rarity": "稀有",
        },
    ]

    result, fingerprint = build_search_selection_query_result(
        context,
        items,
        collectible_artifacts={"relic_test": collectible_artifact},
    )

    groups = result.data["groups"]
    assert [group["type"] for group in groups] == [item["type"] for item in items]
    assert [group["items"][0]["index"] for group in groups] == list(
        range(1, 8)
    )
    assert groups[0]["layout"] == "portrait"
    assert groups[2]["layout"] == "stage"
    assert groups[1]["css_class"] == "enemy"
    assert groups[5]["css_class"] == "material"
    assert groups[6]["css_class"] == "collectible"
    assert all(group["items"][0]["image_data"].startswith("data:image/png;base64,") for group in groups)
    assert len(fingerprint) == 64

    loader = JinjaTemplateLoader(str(PROJECT_ROOT / "data" / "templates"))
    html = JinjaHtmlRenderer(loader).render("search_selection", result).payload
    assert "测试干员" in html
    assert "测试关卡" in html
    assert "测试藏品" in html
    assert "回复序号或名称继续查询" in html
    assert "search-card-test" not in html


def test_search_selection_card_groups_mechanism_items(tmp_path: Path) -> None:
    context, collectible_artifact = _card_context(tmp_path)
    items = [
        {
            "id": "rogue_3_totem_R_L1",
            "name": "黜人",
            "type": "密文板",
            "topic_name": "探索者的银凇止境",
            "sub_type": "上半板",
            "rarity": "普通",
        },
        {
            "id": "rogue_5_copper_B_01_a",
            "name": "大炎通宝",
            "type": "通宝",
            "topic_name": "岁的界园志异",
            "variant_count": 11,
        },
    ]

    result, _ = build_search_selection_query_result(
        context,
        items,
        collectible_artifacts={
            "rogue_3_totem_R_L1": collectible_artifact,
        },
    )

    groups = result.data["groups"]
    assert [group["type"] for group in groups] == ["密文板", "通宝"]
    assert all(group["css_class"] == "collectible" for group in groups)
    assert groups[0]["items"][0]["subtitle"] == "探索者的银凇止境"
    assert groups[0]["items"][0]["meta"] == "上半板 · 普通"
    assert groups[0]["items"][0]["image_data"].startswith(
        "data:image/png;base64,"
    )
    assert groups[1]["items"][0]["meta"] == "11种变体"


def test_result_cache_key_uses_all_ids_in_original_order_without_join_ambiguity() -> None:
    first = build_search_result_cache_key([{"id": "ab"}, {"id": "c"}])
    second = build_search_result_cache_key([{"id": "a"}, {"id": "bc"}])
    reordered = build_search_result_cache_key([{"id": "c"}, {"id": "ab"}])
    same = build_search_result_cache_key([{"id": "ab"}, {"id": "c"}])

    assert first.startswith("r_") and len(first) == 66
    assert first == same
    assert first != second
    assert first != reordered

    first_twenty = [{"id": f"item-{index}"} for index in range(20)]
    twenty_one = [*first_twenty, {"id": "item-20"}]
    assert build_search_result_cache_key(first_twenty) != build_search_result_cache_key(
        twenty_one
    )


def test_search_card_cache_rebuilds_changed_content_and_prunes_lru(
    tmp_path: Path,
) -> None:
    cfg = SimpleNamespace(
        ResourcePath=tmp_path,
        SearchCardCacheMaxEntries=2,
        SearchCardCacheMaxBytes=1024 * 1024,
        SearchCardCacheMaxEntryBytes=128 * 1024,
    )
    cache = SearchCardCache(cfg)
    render_calls: dict[str, int] = {}

    async def render(cache_key: str, content: bytes):
        render_calls[cache_key] = render_calls.get(cache_key, 0) + 1
        entry_dir = cache.root / cache_key
        entry_dir.mkdir(parents=True, exist_ok=True)
        path = entry_dir / "artifact.png"
        path.write_bytes(content)
        (entry_dir / "artifact.html").write_text("html", encoding="utf-8")
        return CardArtifact("search_selection", cache_key, "png", path)

    keys = [
        build_search_result_cache_key([{"id": f"item-{index}"}])
        for index in range(3)
    ]

    async def scenario() -> None:
        await cache.get_or_render(
            cache_key=keys[0],
            fingerprint="v1",
            render=lambda: render(keys[0], b"one"),
        )
        first_access = cache.root / keys[0] / ".access"
        os.utime(first_access, ns=(1, 1))

        hit = await cache.get_or_render(
            cache_key=keys[0],
            fingerprint="v1",
            render=lambda: render(keys[0], b"unused"),
        )
        assert hit is not None
        assert render_calls[keys[0]] == 1

        rebuilt = await cache.get_or_render(
            cache_key=keys[0],
            fingerprint="v2",
            render=lambda: render(keys[0], b"changed"),
        )
        assert rebuilt is not None
        assert render_calls[keys[0]] == 2

        await cache.get_or_render(
            cache_key=keys[1],
            fingerprint="v1",
            render=lambda: render(keys[1], b"two"),
        )
        os.utime(cache.root / keys[0] / ".access", ns=(1, 1))
        os.utime(cache.root / keys[1] / ".access", ns=(2, 2))
        await cache.get_or_render(
            cache_key=keys[2],
            fingerprint="v1",
            render=lambda: render(keys[2], b"three"),
        )

    asyncio.run(scenario())

    assert not (cache.root / keys[0]).exists()
    assert (cache.root / keys[1] / "artifact.png").is_file()
    assert (cache.root / keys[2] / "artifact.png").is_file()


def test_query_search_reuses_card_for_aliases_with_same_ordered_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # AI-CORRECTION 2026-11-10: 搜索与组装已解耦；同别名候选的卡片复用
    # 现通过显式调用 query_search_card 验证，同时确认搜索本身不渲染。
    _write_asset(tmp_path, "assets/enemy/enemy_a.png")
    _write_asset(tmp_path, "assets/enemy/enemy_b.png")
    items = [
        {
            "id": "enemy_a",
            "name": "敌人甲",
            "type": "敌人",
            "enemy_index": "A1",
            "enemy_level": "普通",
        },
        {
            "id": "enemy_b",
            "name": "敌人乙",
            "type": "敌人",
            "enemy_index": "A2",
            "enemy_level": "精英",
        },
    ]
    monkeypatch.setattr(
        search_queries,
        "search",
        lambda *_args, **_kwargs: QueryExecutionResult(
            data={"items": [dict(item) for item in items]}
        ),
    )

    async def no_collectibles(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(
        search_queries,
        "attach_collectible_icon_artifacts",
        no_collectibles,
    )

    class FakeCardService:
        def __init__(self):
            self.calls = 0

        async def get(self, *, template, payload_key, payload, format):
            self.calls += 1
            path = (
                tmp_path
                / "cache"
                / "cards"
                / template
                / payload_key
                / f"artifact.{format}"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(PNG_BYTES)
            return CardArtifact(template, payload_key, format, path)

    cfg = SimpleNamespace(
        ProjectRoot=PROJECT_ROOT,
        ResourcePath=tmp_path,
        BaseUrl="https://example.test/",
        SearchCardCacheMaxEntries=128,
        SearchCardCacheMaxBytes=256 * 1024 * 1024,
        SearchCardCacheMaxEntryBytes=16 * 1024 * 1024,
    )
    card_service = FakeCardService()
    context = SimpleNamespace(
        cfg=cfg,
        data_repository=SimpleNamespace(
            get_bundle=lambda: SimpleNamespace(
                version="v1",
                operators={},
                materials={},
                enemies={
                    item["id"]: SimpleNamespace(
                        id=item["id"],
                        name=item["name"],
                        index=item["enemy_index"],
                        enemy_level=item["enemy_level"],
                    )
                    for item in items
                },
            )
        ),
        card_service=card_service,
        prefer_local_artifact_path=True,
    )

    first = asyncio.run(search_queries.query_search(context, "别名甲"))
    second = asyncio.run(search_queries.query_search(context, "别名乙"))

    assert first.image_url is None and first.image_path is None
    assert second.image_url is None and second.image_path is None
    assert first.data["items"] == items
    assert card_service.calls == 0

    first = asyncio.run(search_queries.query_search_card(
        context, [item["id"] for item in first.data["items"]]
    ))
    second = asyncio.run(search_queries.query_search_card(
        context, [item["id"] for item in second.data["items"]]
    ))
    assert first.image_url == second.image_url
    assert first.image_url is not None
    assert card_service.calls == 1
    assert first.image_path and Path(first.image_path).is_file()

    reordered = asyncio.run(search_queries.query_search_card(
        context, ["enemy_b", "enemy_a"]
    ))
    assert [item["id"] for item in reordered.data["items"]] == ["enemy_b", "enemy_a"]
    assert reordered.image_url != first.image_url
    assert card_service.calls == 2

    selected = asyncio.run(search_queries.query_search_card(context, ["enemy_b"]))
    assert selected.data["items"] == [items[1]]
    assert selected.image_url is not None
    assert card_service.calls == 3


@pytest.mark.parametrize("ids, message", [
    ([], "1~20"),
    ([f"item-{index}" for index in range(21)], "1~20"),
    ("enemy_a", "1~20"),
    ([""], "非空字符串"),
    (["   "], "非空字符串"),
    ([None], "非空字符串"),
    ([123], "非空字符串"),
    (["enemy_a", " enemy_a "], "重复"),
])
def test_search_card_rejects_invalid_selection_before_loading_data(ids, message):
    result = asyncio.run(search_queries.query_search_card(SimpleNamespace(), ids))
    assert message in result.message
    assert result.data is None
    assert result.image_url is None


def _selection_context(tmp_path: Path):
    context, _ = _card_context(tmp_path)
    bundle = context.data_repository.get_bundle()
    bundle.operators["char_test"].id = "char_test"
    bundle.operators["char_test"].name = "测试干员"
    bundle.operators["char_test"].token_ids = ["token_test"]
    bundle.tokens = {
        "token_test": SimpleNamespace(id="token_test", name="测试召唤物"),
        "token_orphan": SimpleNamespace(id="token_orphan", name="无主召唤物"),
    }
    bundle.skins = {
        "char_test@skin#1": SimpleNamespace(
            skin_id="char_test@skin#1", name="测试皮肤",
            operator_id="char_test", operator_name="测试干员",
        ),
    }
    bundle.materials["material_test"].update(id="material_test", name="测试材料")
    bundle.stages = {
        "stage_test": SimpleNamespace(
            id="stage_test", name="测试关卡", code="T-1",
            difficulty="FOUR_STAR", stage_type="ACTIVITY",
        ),
    }
    bundle.enemies = {
        "enemy_test": SimpleNamespace(
            id="enemy_test", name="测试敌人", index="X1", enemy_level="ELITE",
        ),
    }
    bundle.integrated_strategy_items = {
        "relic_test": {
            "id": "relic_test", "name": "测试藏品", "game_type": "RELIC",
            "topic_name": "测试主题", "usage": "测试效果",
        },
        "totem_test": {
            "id": "totem_test", "name": "测试密文板", "game_type": "TOTEM",
            "display_type": "密文板", "sub_type_name": "上半板",
            "topic_name": "测试主题", "usage": "测试机制效果",
        },
    }
    bundle.operator_name_to_id = {"测试干员": "char_test"}
    bundle.token_name_to_id = {"测试召唤物": "token_test"}
    bundle.skin_name_to_id = {"测试皮肤": "char_test@skin#1"}
    bundle.material_name_to_id = {"测试材料": "material_test"}
    bundle.stage_alias_to_ids = {"测试关卡": ["stage_test"]}
    bundle.enemy_alias_to_ids = {"测试敌人": ["enemy_test"]}
    bundle.integrated_strategy_item_alias_to_ids = {
        "测试藏品": ["relic_test"], "测试密文板": ["totem_test"],
    }
    context.data_repository.is_ready = lambda: True
    context.prefer_local_artifact_path = True

    class FakeCardService:
        def __init__(self):
            self.payloads = []

        async def get(self, *, template, payload_key, payload, format):
            self.payloads.append(payload)
            path = tmp_path / "cache" / "cards" / template / payload_key / f"artifact.{format}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(PNG_BYTES)
            return CardArtifact(template, payload_key, format, path)

    context.card_service = FakeCardService()
    return context


def test_search_card_resolves_mixed_ids_without_prior_search_and_numbers_selection(tmp_path):
    context = _selection_context(tmp_path)
    ids = [
        "totem_test", "char_test", "stage_test", "relic_test", "token_test",
        "char_test@skin#1", "enemy_test", "material_test",
    ]
    result = asyncio.run(search_queries.query_search_card(context, ids))
    items = result.data["items"]
    assert [item["id"] for item in items] == ids
    assert [item["type"] for item in items] == [
        "密文板", "干员", "关卡", "集成战略藏品", "召唤物", "皮肤", "敌人", "材料",
    ]
    assert items[0]["usage"] == "测试机制效果"
    assert items[0]["sub_type"] == "上半板"
    assert items[2]["difficulty"] == "突袭"
    assert items[3]["usage"] == "测试效果"
    assert items[4]["operator_id"] == "char_test"
    assert items[5]["operator_name"] == "测试干员"
    assert items[6]["enemy_level"] == "精英"
    assert result.image_url is not None
    card = context.card_service.payloads[0]
    displayed = [item for group in card.data["groups"] for item in group["items"]]
    assert [(item["index"], item["id"]) for item in displayed] == list(enumerate(ids, 1))
    assert card.data["remaining"] == 0

    normalized = asyncio.run(search_queries.query_search_card(
        context, [f" {item_id} " for item_id in ids]
    ))
    assert normalized.image_url == result.image_url
    assert len(context.card_service.payloads) == 1


def test_mcp_search_then_build_card_shows_only_context_selected_ids(tmp_path):
    from mcp.server.fastmcp import FastMCP

    from src.adapters.mcp.mcp_tools.search import register_search_tool

    context = _selection_context(tmp_path)
    app = SimpleNamespace(state=SimpleNamespace())
    mcp = FastMCP("search-card-test")
    register_search_tool(mcp, app)

    async def call_tool(name, arguments):
        content = await mcp.call_tool(name, arguments)
        return json.loads(content[0].text)

    async def scenario():
        unavailable = await call_tool("build_search_card", {"ids": ["enemy_test"]})
        assert unavailable == {"message": "未初始化数据上下文"}

        app.state.ctx = context
        candidates = await call_tool("search", {"query": "测试"})
        assert len(candidates["data"]["items"]) > 2
        assert "card_image_url" not in candidates
        assert "image_path" not in candidates
        assert context.card_service.payloads == []

        ids = ["enemy_test", "char_test"]
        assert set(ids) <= {item["id"] for item in candidates["data"]["items"]}
        card = await call_tool("build_search_card", {"ids": ids})
        assert [item["id"] for item in card["data"]["items"]] == ids
        assert card["card_image_url"].endswith("/artifact.png")
        displayed = context.card_service.payloads[0].data["groups"]
        assert [(group["items"][0]["index"], group["items"][0]["id"]) for group in displayed] == list(enumerate(ids, 1))

    asyncio.run(scenario())


@pytest.mark.parametrize("unknown_id", ["missing", "token_orphan", "../../escape"])
def test_search_card_rejects_unknown_id_without_rendering_partial_card(tmp_path, unknown_id):
    context = _selection_context(tmp_path)
    result = asyncio.run(search_queries.query_search_card(context, ["char_test", unknown_id]))
    assert unknown_id in result.message
    assert result.data is None
    assert result.image_url is None
    assert context.card_service.payloads == []


def test_search_card_render_failure_preserves_only_selected_items(tmp_path):
    context = _selection_context(tmp_path)

    async def fail_render(**_kwargs):
        raise RuntimeError("renderer unavailable")

    context.card_service.get = fail_render
    result = asyncio.run(search_queries.query_search_card(context, ["enemy_test"]))
    assert [item["id"] for item in result.data["items"]] == ["enemy_test"]
    assert result.image_url is None
    assert "生成搜索卡片失败" in result.message


def test_search_without_matches_or_with_unavailable_icons_never_builds_card(tmp_path, monkeypatch):
    context = _selection_context(tmp_path)

    async def fail_icons(*_args, **_kwargs):
        raise OSError("icon unavailable")

    monkeypatch.setattr(search_queries, "attach_collectible_icon_artifacts", fail_icons)
    for result in (
        QueryExecutionResult(message="query 不能为空"),
        QueryExecutionResult(message="未找到匹配"),
        QueryExecutionResult(data={"items": []}),
        QueryExecutionResult(data={"items": [{"id": "relic_test"}]}),
    ):
        monkeypatch.setattr(search_queries, "search", lambda *_args, **_kwargs: result)
        assert asyncio.run(search_queries.query_search(context, "测试")) is result
        assert result.image_url is None
    assert context.card_service.payloads == []


def test_oversized_search_card_is_removed_and_not_returned(tmp_path: Path) -> None:
    cfg = SimpleNamespace(
        ResourcePath=tmp_path,
        SearchCardCacheMaxEntries=2,
        SearchCardCacheMaxBytes=64,
        SearchCardCacheMaxEntryBytes=32,
    )
    cache = SearchCardCache(cfg)
    cache_key = build_search_result_cache_key([{"id": "oversized"}])

    async def render():
        path = cache.root / cache_key / "artifact.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 64)
        return CardArtifact("search_selection", cache_key, "png", path)

    artifact = asyncio.run(
        cache.get_or_render(
            cache_key=cache_key,
            fingerprint="v1",
            render=render,
        )
    )

    assert artifact is None
    assert not (cache.root / cache_key).exists()


def test_search_card_cache_respects_total_byte_limit(tmp_path: Path) -> None:
    cfg = SimpleNamespace(
        ResourcePath=tmp_path,
        SearchCardCacheMaxEntries=10,
        SearchCardCacheMaxBytes=520,
        SearchCardCacheMaxEntryBytes=260,
    )
    cache = SearchCardCache(cfg)
    keys = [
        build_search_result_cache_key([{"id": f"byte-item-{index}"}])
        for index in range(4)
    ]

    async def render(cache_key: str):
        path = cache.root / cache_key / "artifact.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 100)
        return CardArtifact("search_selection", cache_key, "png", path)

    async def scenario() -> None:
        for cache_key in keys:
            await cache.get_or_render(
                cache_key=cache_key,
                fingerprint="v1",
                render=lambda key=cache_key: render(key),
            )

    asyncio.run(scenario())

    entries = cache._scan_entries()
    assert sum(size for _key, _access, size in entries) <= cfg.SearchCardCacheMaxBytes
    assert len(entries) < len(keys)
