from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from src.app.services.operator_queries import search
from src.app.services.search_aliases import (
    SEARCH_ALIAS_SOURCE_URL,
    SEARCH_ALIAS_SYNC_INTERVAL_SECONDS,
    SearchAliasRepository,
    SearchAliasSnapshot,
)


def _payload(rows: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {"code": 200, "data": rows, "message": ""},
        ensure_ascii=False,
    ).encode("utf-8")


def test_alias_sync_deduplicates_rows_and_keeps_only_active_globals(
    monkeypatch,
) -> None:
    repository = SearchAliasRepository()
    payload = _payload(
        [
            {
                "origin": "艾雅法拉",
                "replace": "小羊",
                "is_global": 1,
                "is_active": 1,
            },
            {
                "origin": "艾雅法拉",
                "replace": "小羊",
                "is_global": 1,
                "is_active": 1,
            },
            {
                "origin": "纯烬艾雅法拉",
                "replace": "小羊",
                "is_global": 1,
                "is_active": 1,
            },
            {
                "origin": "银灰",
                "replace": "银老板",
                "is_global": 0,
                "is_active": 1,
            },
            {
                "origin": "棘刺",
                "replace": "鸡翅",
                "is_global": 1,
                "is_active": 0,
            },
        ]
    )
    monkeypatch.setattr(repository, "_download", lambda: payload)

    result = asyncio.run(repository.sync())
    snapshot = repository.get_snapshot()

    assert result.ok is True
    assert result.alias_count == 1
    assert result.source_record_count == 5
    assert snapshot.alias_to_origins == {
        "小羊": ("艾雅法拉", "纯烬艾雅法拉")
    }
    assert snapshot.synced_at is not None


def test_failed_alias_sync_keeps_last_successful_snapshot(monkeypatch) -> None:
    repository = SearchAliasRepository()
    monkeypatch.setattr(
        repository,
        "_download",
        lambda: _payload([{"origin": "艾雅法拉", "replace": "小羊"}]),
    )
    assert asyncio.run(repository.sync()).ok is True
    previous = repository.get_snapshot()

    def fail_download() -> bytes:
        raise TimeoutError("timeout")

    monkeypatch.setattr(repository, "_download", fail_download)
    result = asyncio.run(repository.sync())

    assert result.ok is False
    assert repository.get_snapshot() is previous
    assert result.alias_count == 1


def test_legacy_http_exception_is_limited_to_the_official_endpoint() -> None:
    assert SEARCH_ALIAS_SYNC_INTERVAL_SECONDS == 60 * 60
    SearchAliasRepository(source_url=SEARCH_ALIAS_SOURCE_URL)

    try:
        SearchAliasRepository(
            source_url="http://106.52.139.57:8000/replace/other"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("unexpected legacy HTTP URL was accepted")


def test_periodic_alias_sync_runs_immediately_and_repeats(monkeypatch) -> None:
    from src.entrypoints import uvicorn_host

    class FakeRepository:
        def __init__(self) -> None:
            self.calls = 0
            self.repeated = asyncio.Event()

        async def sync(self):
            self.calls += 1
            if self.calls >= 2:
                self.repeated.set()
            return SimpleNamespace(
                ok=True,
                alias_count=1,
                source_record_count=1,
            )

    class FakeContext:
        def __init__(self, repository) -> None:
            self.search_alias_repository = repository

    async def run_loop() -> int:
        repository = FakeRepository()
        app = SimpleNamespace(
            state=SimpleNamespace(ctx=FakeContext(repository))
        )
        task = asyncio.create_task(
            uvicorn_host._periodic_alias_sync_loop(
                app,
                interval_seconds=0.001,
            )
        )
        try:
            await asyncio.wait_for(repository.repeated.wait(), timeout=1)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return repository.calls

    monkeypatch.setattr(uvicorn_host, "AppContext", FakeContext)

    assert asyncio.run(run_loop()) >= 2


def _search_context(alias_to_origins: dict[str, tuple[str, ...]]):
    operators = {
        "char_eyja": SimpleNamespace(
            id="char_eyja",
            name="艾雅法拉",
            token_ids=[],
        ),
        "char_skadi": SimpleNamespace(
            id="char_skadi",
            name="斯卡蒂",
            token_ids=[],
        ),
        "char_w": SimpleNamespace(id="char_w", name="W", token_ids=[]),
    }
    enemies = {
        "enemy_pat": SimpleNamespace(
            id="enemy_pat",
            name="爱国者",
            index="PT",
            enemy_level="BOSS",
        ),
        "enemy_w": SimpleNamespace(
            id="enemy_w",
            name="W",
            index="W",
            enemy_level="BOSS",
        ),
    }
    bundle = SimpleNamespace(
        version="alias-test",
        operators=operators,
        operator_name_to_id={
            "艾雅法拉": "char_eyja",
            "斯卡蒂": "char_skadi",
            "W": "char_w",
        },
        operator_index_to_id={},
        tokens={},
        token_name_to_id={},
        skins={},
        skin_name_to_id={},
        materials={
            "30014": {"id": "30014", "name": "提纯源岩"},
        },
        material_name_to_id={"提纯源岩": "30014"},
        stages={},
        stage_alias_to_ids={},
        enemies=enemies,
        enemy_alias_to_ids={
            "爱国者": ["enemy_pat"],
            "W": ["enemy_w"],
        },
        integrated_strategy_collectibles={},
        integrated_strategy_collectible_alias_to_ids={},
    )
    snapshot = SearchAliasSnapshot(alias_to_origins=alias_to_origins)
    return SimpleNamespace(
        data_repository=SimpleNamespace(get_bundle=lambda: bundle),
        search_alias_repository=SimpleNamespace(
            get_snapshot=lambda: snapshot
        ),
    )


def test_aliases_join_unified_fuzzy_search_without_alias_result_type() -> None:
    context = _search_context(
        {
            "小羊": ("艾雅法拉",),
            "大石头": ("提纯源岩",),
            "大爹": ("爱国者",),
        }
    )

    fuzzy_items = search(context, "小羔", limit=10).to_response()["data"][
        "items"
    ]
    operator = next(item for item in fuzzy_items if item["id"] == "char_eyja")
    material = search(context, "大石头", limit=10).to_response()["data"][
        "items"
    ][0]
    enemy = search(context, "大爹", limit=10).to_response()["data"][
        "items"
    ][0]

    assert operator == {
        "id": "char_eyja",
        "name": "艾雅法拉",
        "type": "干员",
        "from_alias": "小羊",
    }
    assert material == {
        "id": "30014",
        "name": "提纯源岩",
        "type": "材料",
        "from_alias": "大石头",
    }
    assert enemy == {
        "id": "enemy_pat",
        "name": "爱国者",
        "type": "敌人",
        "enemy_index": "PT",
        "enemy_level": "BOSS",
        "from_alias": "大爹",
    }
    assert all(item.get("type") != "别名" for item in fuzzy_items)


def test_alias_chain_and_cross_type_targets_are_preserved() -> None:
    context = _search_context(
        {
            "先蒂": ("蒂蒂",),
            "蒂蒂": ("斯卡蒂",),
            "蟑螂": ("W",),
        }
    )

    chained = search(context, "先蒂", limit=10).to_response()["data"][
        "items"
    ][0]
    ambiguous = search(context, "蟑螂", limit=10).to_response()["data"][
        "items"
    ]

    assert chained == {
        "id": "char_skadi",
        "name": "斯卡蒂",
        "type": "干员",
        "from_alias": "先蒂",
    }
    assert {(item["id"], item["type"]) for item in ambiguous} == {
        ("char_w", "干员"),
        ("enemy_w", "敌人"),
    }
    assert {item["from_alias"] for item in ambiguous} == {"蟑螂"}


def test_formal_name_match_does_not_report_from_alias() -> None:
    context = _search_context({"小羊": ("艾雅法拉",)})

    items = search(context, "艾雅法拉", limit=10).to_response()["data"][
        "items"
    ]
    operator = next(item for item in items if item["id"] == "char_eyja")

    assert operator == {
        "id": "char_eyja",
        "name": "艾雅法拉",
        "type": "干员",
    }
