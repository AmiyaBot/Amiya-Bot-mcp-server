from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.app.config import Config
from src.app.remote_download_manager import (
    RemoteDownloadManager,
    RemoteDownloadResult,
)
from src.app.services import integrated_strategy_collectible_assets
from src.app.services.operator_queries import search
from src.data.repository.bundle.bundle_builder import load_bundle_from_disk


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
        "topic_id": "rogue_5",
        "topic_name": "岁的界园志异",
        "icon_id": "rogue_5_relic_legacy_11",
        "description": "“天有洪炉，地生五金”......虽然可以用来成就各种事业，却没人知道具体原理。",
        "usage": "立即进阶三个干员（不消耗希望）",
        "rarity": "超稀有",
        "unlock_condition": "在多局游戏中累计进阶总共35名干员",
        "can_sacrifice": True,
    }


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
    assert requests[0].allowed_hosts == frozenset({"torappu.prts.wiki"})


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
