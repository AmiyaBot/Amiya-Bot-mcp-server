from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

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
            )
        ),
        card_service=card_service,
        prefer_local_artifact_path=True,
    )

    first = asyncio.run(search_queries.query_search(context, "别名甲"))
    second = asyncio.run(search_queries.query_search(context, "别名乙"))

    assert first.image_url == second.image_url
    assert card_service.calls == 1
    assert first.image_path and Path(first.image_path).is_file()


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
