from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from src.app.config import Config
from src.app.card_service import CardService
from src.app.remote_download_manager import (
    RemoteDownloadManager,
    RemoteDownloadResult,
)
from src.app.services import integrated_strategy_collectible_assets
from src.app.services import integrated_strategy_item_queries
from src.app.services.integrated_strategy_collectible_queries import (
    query_integrated_strategy_collectible_by_id,
)
from src.app.services.integrated_strategy_item_queries import (
    query_integrated_strategy_item_by_id,
)
from src.app.services.operator_queries import search
from src.data.repository.bundle.bundle_builder import (
    _build_integrated_strategy_items,
    load_bundle_from_disk,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def collectible_context():
    cfg = Config(
        ProjectRoot=PROJECT_ROOT,
        ResourcePath=PROJECT_ROOT / "resources",
        GameDataRepo="local-test",
        BaseUrl="https://example.test",
    )
    bundle = load_bundle_from_disk(cfg, version="collectible-test")
    context = SimpleNamespace(
        cfg=cfg,
        data_repository=SimpleNamespace(get_bundle=lambda: bundle),
    )
    return context, bundle


def test_bundle_contains_only_relic_items_with_topic_metadata(collectible_context):
    _, bundle = collectible_context

    collectible = bundle.integrated_strategy_collectibles["rogue_5_relic_legacy_11"]
    assert collectible["name"] == "古旧铸物"
    assert collectible["usage"] == "立即进阶三个干员（不消耗希望）"
    assert collectible["unlock_condition"] == "在多局游戏中累计进阶总共35名干员"
    assert collectible["topic_id"] == "rogue_5"
    assert collectible["topic_name"] == "岁的界园志异"
    assert all(
        item["raw"]["type"] == "RELIC"
        for item in bundle.integrated_strategy_collectibles.values()
    )
    assert "先锋招募券" not in bundle.integrated_strategy_collectible_alias_to_ids


def test_collectible_is_available_from_unified_search(collectible_context):
    context, _ = collectible_context

    items = search(context, "古旧铸物", limit=10).to_response()["data"]["items"]
    collectibles = [item for item in items if item.get("type") == "集成战略藏品"]

    collectible = next(
        item
        for item in collectibles
        if item["id"] == "rogue_5_relic_legacy_11"
    )
    assert collectible == {
        "id": "rogue_5_relic_legacy_11",
        "name": "古旧铸物",
        "type": "集成战略藏品",
        "game_type": "RELIC",
        "topic_id": "rogue_5",
        "topic_name": "岁的界园志异",
        "icon_id": "rogue_5_relic_legacy_11",
        "description": "“天有洪炉，地生五金”......虽然可以用来成就各种事业，却没人知道具体原理。",
        "usage": "立即进阶三个干员（不消耗希望）",
        "rarity": "超稀有",
        "unlock_condition": "在多局游戏中累计进阶总共35名干员",
        "can_exchange": True,
    }


def test_theme_mechanism_items_are_grouped_and_searchable(collectible_context):
    context, bundle = collectible_context

    type_counts = {}
    for item in bundle.integrated_strategy_items.values():
        type_counts[item["display_type"]] = (
            type_counts.get(item["display_type"], 0) + 1
        )

    assert type_counts["剧目"] == 13
    assert type_counts["骰子"] == 3
    assert type_counts["密文板"] == 43
    assert type_counts["构想"] == 54
    assert type_counts["通宝"] == 106
    assert all(
        item["game_type"] != "COPPER_BUFF"
        for item in bundle.integrated_strategy_items.values()
    )

    play = [
        item
        for item in search(
            context,
            "凯旋颂",
            limit=10,
        ).to_response()["data"]["items"]
        if item["type"] == "剧目"
    ]
    assert len(play) == 1
    assert play[0]["type"] == "剧目"
    assert [variant["variant_name"] for variant in play[0]["variants"]] == [
        "普通",
        "猩红",
    ]

    dice = [
        item
        for item in search(
            context,
            "六面骰子",
            limit=10,
        ).to_response()["data"]["items"]
        if item["type"] == "骰子"
    ]
    assert len(dice) == 1
    assert dice[0]["type"] == "骰子"
    assert [variant["variant_name"] for variant in dice[0]["variants"]] == [
        "常规",
        "作战内",
    ]

    totem = [
        item
        for item in search(
            context,
            "黜人",
            limit=10,
        ).to_response()["data"]["items"]
        if item["type"] == "密文板"
    ]
    assert len(totem) == 1
    assert totem[0]["type"] == "密文板"
    assert totem[0]["sub_type"] == "上半板"

    fragment = [
        item
        for item in search(
            context,
            "纯白花瓣",
            limit=10,
        ).to_response()["data"]["items"]
        if item["type"] == "构想"
    ]
    assert len(fragment) == 1
    assert fragment[0]["type"] == "构想"
    assert fragment[0]["sub_type"] == "遗愿"

    copper = [
        item
        for item in search(
            context,
            "大炎通宝",
            limit=10,
        ).to_response()["data"]["items"]
        if item["type"] == "通宝"
    ]
    assert len(copper) == 1
    assert copper[0]["type"] == "通宝"
    assert copper[0]["sub_type"] == "衡钱"
    assert copper[0]["variant_count"] == 11
    assert [variant["variant_name"] for variant in copper[0]["variants"]] == [
        "基础",
        "锈色",
        "存护",
        "入幻",
        "引光",
        "巡游",
        "相合",
        "易变",
        "易花",
        "易厉",
        "受引",
    ]
    assert copper[0]["variants"][0]["variant_effect"] == "无额外品相效果"
    assert copper[0]["variants"][1]["variant_effect"] == (
        "投出时，每经过一个节点，获得源石锭+1"
    )

    special_copper = [
        item
        for item in search(
            context,
            "花-鸭爵金币",
            limit=10,
        ).to_response()["data"]["items"]
        if item["type"] == "通宝" and item["name"] == "花-鸭爵金币"
    ]
    assert len(special_copper) == 1
    assert special_copper[0]["variant_count"] == 12
    assert special_copper[0]["variants"][-1]["variant_name"] == "特殊受引"
    assert special_copper[0]["sub_type"] == "花钱"

    money_types = [
        item
        for item in search(
            context,
            "厉钱",
            limit=10,
        ).to_response()["data"]["items"]
        if item["type"] == "通宝"
    ]
    assert money_types
    assert all(item["sub_type"] == "厉钱" for item in money_types)


def test_blackflow_scraps_are_forward_compatible():
    tables = {
        "gamedata": {
            "roguelike_topic_table": {
                "topics": {
                    "rogue_6": {
                        "name": "沉沦者的黑流树海",
                        "sort": 6,
                    }
                },
                "details": {
                    "rogue_6": {
                        "items": {
                            "rogue_6_scrap_G_01": {
                                "id": "rogue_6_scrap_G_01",
                                "name": "种子",
                                "type": "SCRAP",
                            },
                            "rogue_6_scrap_M_01": {
                                "id": "rogue_6_scrap_M_01",
                                "name": "报废轮子",
                                "type": "SCRAP",
                            },
                            "rogue_6_scrap_P_01": {
                                "id": "rogue_6_scrap_P_01",
                                "name": "白模鸟",
                                "type": "SCRAP",
                            },
                        }
                    }
                },
            }
        }
    }

    items, aliases = _build_integrated_strategy_items(tables)

    assert {
        item["display_type"] for item in items.values()
    } == {"零件"}
    assert items["rogue_6_scrap_G_01"]["sub_type_name"] == "自然物"
    assert items["rogue_6_scrap_M_01"]["sub_type_name"] == "加工品"
    assert items["rogue_6_scrap_P_01"]["sub_type_name"] == "概念体"
    assert aliases["加工品"] == ["rogue_6_scrap_M_01"]


def test_same_name_items_with_different_effects_are_not_merged(
    collectible_context,
):
    context, _ = collectible_context

    items = [
        item
        for item in search(
            context,
            "衡-捕风",
            limit=10,
        ).to_response()["data"]["items"]
        if item["type"] == "通宝" and item["name"] == "衡-捕风"
    ]

    assert len(items) == 4
    assert len({item["id"] for item in items}) == 4
    assert len({item["usage"] for item in items}) == 4


def test_same_name_collectibles_from_different_topics_are_preserved(
    collectible_context,
):
    context, _ = collectible_context

    items = search(context, "热水壶", limit=10).to_response()["data"]["items"]
    collectibles = [item for item in items if item.get("type") == "集成战略藏品"]

    assert {item["topic_id"] for item in collectibles} == {
        "rogue_1",
        "rogue_2",
        "rogue_3",
        "rogue_4",
        "rogue_5",
    }
    assert len({item["id"] for item in collectibles}) == 5


def test_collectible_id_is_searchable_case_insensitively(collectible_context):
    context, _ = collectible_context

    items = search(
        context,
        "ROGUE_5_RELIC_LEGACY_11",
        limit=10,
    ).to_response()["data"]["items"]

    assert any(
        item.get("id") == "rogue_5_relic_legacy_11"
        and item.get("type") == "集成战略藏品"
        for item in items
    )


def test_prts_icon_path_uses_game_data_icon_id():
    assert (
        integrated_strategy_collectible_assets.build_collectible_icon_source_url(
            "rogue_5_relic_legacy_11"
        )
        == "https://torappu.prts.wiki/assets/roguelike_topic_itempic/"
        "rogue_5_relic_legacy_11.png"
    )
    assert (
        integrated_strategy_collectible_assets.build_collectible_icon_source_url(
            "../invalid"
        )
        is None
    )
    assert integrated_strategy_collectible_assets.build_collectible_icon_source_urls(
        "rogue_1_capsule_1"
    )[-1].endswith(
        "/8/82/%E9%9B%86%E6%88%90%E6%88%98%E7%95%A5_2_"
        "%E5%89%A7%E7%9B%AE_1.png"
    )
    assert integrated_strategy_collectible_assets.build_collectible_icon_source_urls(
        "rogue_2_dice_11"
    )[-1].endswith(
        "/f/f3/%E5%A4%B4%E5%83%8F_%E8%A3%85%E7%BD%AE_8%E9%9D%A2"
        "%E9%AA%B0%E5%AD%90.png"
    )
    assert integrated_strategy_collectible_assets.build_collectible_icon_source_urls(
        "rogue_5_copper_B_01_a"
    )[-1].endswith("/rogue_5_copper_B_01.png")


def test_prts_icon_is_downloaded_once_and_reused_from_cache(
    tmp_path: Path,
    monkeypatch,
):
    png_payload = integrated_strategy_collectible_assets.PNG_SIGNATURE + b"test-png"
    requests = []
    download_manager = RemoteDownloadManager(max_concurrency=2)

    def fake_download(request):
        requests.append(request)
        return RemoteDownloadResult(
            payload=png_payload,
            content_type="image/png",
            final_url=request.url,
        )

    monkeypatch.setattr(download_manager, "_download_sync", fake_download)
    integrated_strategy_collectible_assets._download_locks.clear()
    integrated_strategy_collectible_assets._missing_icon_ids.clear()
    context = SimpleNamespace(
        cfg=SimpleNamespace(
            ResourcePath=tmp_path,
            BaseUrl="https://example.test/",
        ),
        prefer_local_artifact_path=False,
        download_manager=download_manager,
    )

    first = asyncio.run(
        integrated_strategy_collectible_assets.resolve_collectible_icon_artifact(
            context,
            "rogue_5_relic_legacy_11",
        )
    )
    second = asyncio.run(
        integrated_strategy_collectible_assets.resolve_collectible_icon_artifact(
            context,
            "rogue_5_relic_legacy_11",
        )
    )

    assert first is not None
    assert second is not None
    assert first.path.read_bytes() == png_payload
    assert first.url == (
        "https://example.test/integrated-strategy-collectible-icons/"
        "rogue_5_relic_legacy_11.png"
    )
    assert second.path == first.path
    assert len(requests) == 1
    assert requests[0].url.endswith("/rogue_5_relic_legacy_11.png")
    assert requests[0].timeout_seconds == 10
    assert requests[0].allowed_hosts == frozenset(
        {"torappu.prts.wiki", "media.prts.wiki"}
    )


def test_mechanism_icon_falls_back_to_prts_wiki_filename(
    tmp_path: Path,
    monkeypatch,
):
    png_payload = integrated_strategy_collectible_assets.PNG_SIGNATURE + b"fallback"
    requests = []
    download_manager = RemoteDownloadManager(max_concurrency=2)

    def fake_download(request):
        requests.append(request)
        if len(requests) == 1:
            raise HTTPError(request.url, 404, "not found", {}, None)
        return RemoteDownloadResult(
            payload=png_payload,
            content_type="image/png",
            final_url=request.url,
        )

    monkeypatch.setattr(download_manager, "_download_sync", fake_download)
    integrated_strategy_collectible_assets._download_locks.clear()
    integrated_strategy_collectible_assets._missing_icon_ids.clear()
    context = SimpleNamespace(
        cfg=SimpleNamespace(
            ResourcePath=tmp_path,
            BaseUrl="https://example.test/",
        ),
        prefer_local_artifact_path=False,
        download_manager=download_manager,
    )

    artifact = asyncio.run(
        integrated_strategy_collectible_assets.resolve_collectible_icon_artifact(
            context,
            "rogue_1_capsule_1",
        )
    )

    assert artifact is not None
    assert artifact.path.read_bytes() == png_payload
    assert len(requests) == 2
    assert requests[1].url.startswith("https://media.prts.wiki/")


def test_cached_icon_url_is_attached_to_unified_search_payload(
    tmp_path: Path,
    monkeypatch,
):
    png_payload = integrated_strategy_collectible_assets.PNG_SIGNATURE + b"test-png"
    download_manager = RemoteDownloadManager(max_concurrency=2)

    monkeypatch.setattr(
        download_manager,
        "_download_sync",
        lambda request: RemoteDownloadResult(
            payload=png_payload,
            content_type="image/png",
            final_url=request.url,
        ),
    )
    integrated_strategy_collectible_assets._download_locks.clear()
    integrated_strategy_collectible_assets._missing_icon_ids.clear()
    context = SimpleNamespace(
        cfg=SimpleNamespace(
            ResourcePath=tmp_path,
            BaseUrl="https://example.test/",
        ),
        prefer_local_artifact_path=False,
        download_manager=download_manager,
    )
    payload = {
        "data": {
            "items": [
                {
                    "id": "rogue_5_relic_legacy_11",
                    "name": "古旧铸物",
                    "type": "集成战略藏品",
                    "icon_id": "rogue_5_relic_legacy_11",
                },
                {
                    "id": "rogue_3_totem_R_L1",
                    "name": "黜人",
                    "type": "密文板",
                    "icon_id": "rogue_3_totem_R_L1",
                }
            ]
        }
    }

    asyncio.run(
        integrated_strategy_collectible_assets.attach_collectible_icon_artifacts(
            context,
            payload,
        )
    )

    assert payload["data"]["items"][0]["icon_url"] == (
        "https://example.test/integrated-strategy-collectible-icons/"
        "rogue_5_relic_legacy_11.png"
    )
    assert payload["data"]["items"][1]["icon_url"] == (
        "https://example.test/integrated-strategy-collectible-icons/"
        "rogue_3_totem_R_L1.png"
    )


def test_icon_cache_failure_does_not_break_search_payload(monkeypatch):
    async def fail_to_resolve(*_args, **_kwargs):
        raise OSError("read-only cache")

    monkeypatch.setattr(
        integrated_strategy_collectible_assets,
        "resolve_collectible_icon_artifact",
        fail_to_resolve,
    )
    context = SimpleNamespace(
        cfg=SimpleNamespace(ResourcePath=Path("/unused"), BaseUrl=None),
        prefer_local_artifact_path=False,
    )
    payload = {
        "data": {
            "items": [
                {
                    "type": "集成战略藏品",
                    "icon_id": "rogue_5_relic_legacy_11",
                }
            ]
        }
    }

    asyncio.run(
        integrated_strategy_collectible_assets.attach_collectible_icon_artifacts(
            context,
            payload,
        )
    )

    assert "icon_url" not in payload["data"]["items"][0]


def test_collectible_detail_returns_structured_data_and_card(
    collectible_context,
    tmp_path: Path,
    monkeypatch,
):
    _, bundle = collectible_context
    download_manager = RemoteDownloadManager(max_concurrency=2)
    png_payload = integrated_strategy_collectible_assets.PNG_SIGNATURE + b"icon"

    monkeypatch.setattr(
        download_manager,
        "_download_sync",
        lambda request: RemoteDownloadResult(
            payload=png_payload,
            content_type="image/png",
            final_url=request.url,
        ),
    )
    integrated_strategy_collectible_assets._download_locks.clear()
    integrated_strategy_collectible_assets._missing_icon_ids.clear()

    class CaptureTransformer:
        def __init__(self):
            self.inputs = []

        async def transform(self, *, input, cfg=None):
            self.inputs.append((input, cfg))
            return integrated_strategy_collectible_assets.PNG_SIGNATURE + b"card"

    transformer = CaptureTransformer()
    cfg = Config(
        ProjectRoot=PROJECT_ROOT,
        ResourcePath=tmp_path,
        BaseUrl="https://example.test/",
    )
    context = SimpleNamespace(
        cfg=cfg,
        data_repository=SimpleNamespace(get_bundle=lambda: bundle),
        card_service=CardService(cfg, html_to_png=transformer),
        download_manager=download_manager,
        prefer_local_artifact_path=True,
    )

    response = asyncio.run(
        query_integrated_strategy_collectible_by_id(
            context,
            "rogue_5_relic_legacy_11",
        )
    ).to_response()

    assert response["data"]["id"] == "rogue_5_relic_legacy_11"
    assert response["data"]["name"] == "古旧铸物"
    assert response["data"]["topic_name"] == "岁的界园志异"
    assert response["data"]["obtain_approach"] == "在集成战略模式中获得"
    assert response["data"]["can_exchange"] is True
    assert "can_sacrifice" not in response["data"]
    assert response["data"]["icon_url"].endswith(
        "/integrated-strategy-collectible-icons/rogue_5_relic_legacy_11.png"
    )
    assert response["card_image_url"].endswith("/artifact.png")
    assert response["data_url"].endswith("/artifact.json")
    assert Path(response["image_path"]).is_file()
    assert len(transformer.inputs) == 1
    rendered_html, render_cfg = transformer.inputs[0]
    assert "古旧铸物" in rendered_html
    assert "data:image/png;base64," in rendered_html
    assert "可交换" in rendered_html
    assert "可被牺牲" not in rendered_html
    assert "主题代号" not in rendered_html
    assert render_cfg["viewport"]["width"] == 1000

    json_artifact_path = Path(response["image_path"]).with_name("artifact.json")
    json_payload = json.loads(json_artifact_path.read_text(encoding="utf-8"))
    assert json_payload["type"] == "integrated_strategy_collectible"
    assert json_payload["data"]["topic_id"] == "rogue_5"
    assert json_payload["data"]["topic_name"] == "岁的界园志异"


def test_same_name_collectible_ids_generate_unique_detail_cards(
    collectible_context,
    tmp_path: Path,
    monkeypatch,
):
    _, bundle = collectible_context
    download_manager = RemoteDownloadManager(max_concurrency=2)
    monkeypatch.setattr(
        download_manager,
        "_download_sync",
        lambda request: RemoteDownloadResult(
            payload=integrated_strategy_collectible_assets.PNG_SIGNATURE + b"icon",
            content_type="image/png",
            final_url=request.url,
        ),
    )
    integrated_strategy_collectible_assets._download_locks.clear()
    integrated_strategy_collectible_assets._missing_icon_ids.clear()

    class StaticTransformer:
        def __init__(self):
            self.inputs = []

        async def transform(self, *, input, cfg=None):
            self.inputs.append(input)
            return integrated_strategy_collectible_assets.PNG_SIGNATURE + b"card"

    transformer = StaticTransformer()
    cfg = Config(
        ProjectRoot=PROJECT_ROOT,
        ResourcePath=tmp_path,
        BaseUrl="https://example.test/",
    )
    context = SimpleNamespace(
        cfg=cfg,
        data_repository=SimpleNamespace(get_bundle=lambda: bundle),
        card_service=CardService(cfg, html_to_png=transformer),
        download_manager=download_manager,
        prefer_local_artifact_path=False,
    )

    first = asyncio.run(
        query_integrated_strategy_collectible_by_id(
            context,
            "rogue_1_relic_r01",
        )
    ).to_response()
    second = asyncio.run(
        query_integrated_strategy_collectible_by_id(
            context,
            "rogue_2_relic_grace_21",
        )
    ).to_response()

    assert first["data"]["name"] == second["data"]["name"] == "热水壶"
    assert first["data"]["topic_id"] == "rogue_1"
    assert second["data"]["topic_id"] == "rogue_2"
    assert first["card_image_url"] != second["card_image_url"]


def test_collectible_detail_requires_an_existing_unique_id(collectible_context):
    context, _ = collectible_context

    empty = asyncio.run(
        query_integrated_strategy_collectible_by_id(context, "")
    ).to_response()
    missing = asyncio.run(
        query_integrated_strategy_collectible_by_id(context, "热水壶")
    ).to_response()

    assert empty == {"message": "collectible_id 不能为空"}
    assert missing == {"message": "未找到集成战略藏品ID: 热水壶"}


def test_mechanism_item_detail_returns_grouped_variants(
    collectible_context,
    tmp_path: Path,
    monkeypatch,
):
    _, bundle = collectible_context

    async def no_icon(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        integrated_strategy_item_queries,
        "resolve_collectible_icon_artifact",
        no_icon,
    )

    class StaticTransformer:
        def __init__(self):
            self.inputs = []

        async def transform(self, *, input, cfg=None):
            self.inputs.append(input)
            return integrated_strategy_collectible_assets.PNG_SIGNATURE + b"card"

    transformer = StaticTransformer()
    cfg = Config(
        ProjectRoot=PROJECT_ROOT,
        ResourcePath=tmp_path,
        BaseUrl="https://example.test/",
    )
    context = SimpleNamespace(
        cfg=cfg,
        data_repository=SimpleNamespace(get_bundle=lambda: bundle),
        card_service=CardService(cfg, html_to_png=transformer),
        prefer_local_artifact_path=True,
    )

    response = asyncio.run(
        query_integrated_strategy_item_by_id(
            context,
            "rogue_5_copper_B_01_a",
        )
    ).to_response()

    assert response["data"]["name"] == "大炎通宝"
    assert response["data"]["type"] == "通宝"
    assert response["data"]["game_type"] == "COPPER"
    assert response["data"]["variant_count"] == 11
    assert response["data"]["variants"][0]["variant_name"] == "基础"
    assert response["data"]["variants"][-1]["variant_name"] == "受引"
    assert response["data"]["sub_type"] == "衡钱"
    assert response["card_image_url"].endswith("/artifact.png")
    assert response["data_url"].endswith("/artifact.json")
    assert Path(response["image_path"]).is_file()
    json_artifact_path = Path(response["image_path"]).with_name("artifact.json")
    json_payload = json.loads(json_artifact_path.read_text(encoding="utf-8"))
    assert json_payload["type"] == "integrated_strategy_item"
    assert len(transformer.inputs) == 1
    assert "品相一览" in transformer.inputs[0]
    assert "无额外品相效果" in transformer.inputs[0]

    empty = asyncio.run(
        query_integrated_strategy_item_by_id(context, "")
    ).to_response()
    missing = asyncio.run(
        query_integrated_strategy_item_by_id(context, "大炎通宝")
    ).to_response()
    assert empty == {"message": "item_id 不能为空"}
    assert missing == {"message": "未找到集成战略物品ID: 大炎通宝"}
