from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.app.config import Config
from src.app.renderers.jinja_html_renderer import JinjaHtmlRenderer
from src.app.renderers.jinja_json_renderer import JinjaJsonRenderer
from src.app.renderers.jinja_template_loader import JinjaTemplateLoader
from src.app.services.enemy_queries import build_enemy_payload, build_enemy_query_result, query_enemy_by_id
from src.app.services.operator_queries import QueryExecutionResult, search
from src.data.repository.bundle.bundle_builder import load_bundle_from_disk


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def enemy_context():
    cfg = Config(
        ProjectRoot=PROJECT_ROOT,
        ResourcePath=PROJECT_ROOT / "resources",
        GameDataRepo="local-test",
        BaseUrl="https://example.test",
    )
    bundle = load_bundle_from_disk(cfg, version="enemy-test")
    context = SimpleNamespace(
        cfg=cfg,
        data_repository=SimpleNamespace(get_bundle=lambda: bundle),
        prefer_local_artifact_path=False,
    )
    return context, bundle


def test_enemy_bundle_resolves_attribute_inheritance(enemy_context):
    _, bundle = enemy_context

    enemy = bundle.enemies["enemy_1007_slime"]

    assert enemy.name == "源石虫"
    assert enemy.races == [{"id": "infection", "name": "感染生物"}]
    assert [item["level"] for item in enemy.attributes] == [0, 1]
    assert enemy.attributes[1]["max_hp"] == 2050
    assert enemy.attributes[1]["defense"] == 0
    assert enemy.attributes[1]["move_speed"] == 1.0
    assert enemy.attributes[1]["attack_interval"] == 1.7


@pytest.mark.parametrize("query", ["源石虫", "B1", "enemy_1007_slime"])
def test_enemy_is_available_from_unified_search(enemy_context, query):
    context, _ = enemy_context

    items = search(context, query, limit=10).to_response()["data"]["items"]
    enemies = [item for item in items if item.get("type") == "敌人"]

    assert enemies[0] == {
        "id": "enemy_1007_slime",
        "name": "源石虫",
        "type": "敌人",
        "enemy_index": "B1",
        "enemy_level": "普通",
    }


def test_duplicate_enemy_names_return_distinct_candidates(enemy_context):
    context, _ = enemy_context

    items = search(context, "拟南兽", limit=10).to_response()["data"]["items"]
    enemies = [item for item in items if item.get("type") == "敌人"]

    assert {item["id"] for item in enemies} == {"enemy_7051_xbcas", "enemy_7053_xbcasz"}
    assert {item["enemy_index"] for item in enemies} == {"SD44", "SD45"}


def test_hidden_enemy_is_queryable_by_id_but_not_search_index(enemy_context):
    context, bundle = enemy_context
    hidden_id = "enemy_1265_durcar"

    assert bundle.enemies[hidden_id].hide_in_handbook is True
    assert all(hidden_id not in ids for ids in bundle.enemy_alias_to_ids.values())
    result = build_enemy_query_result(context, hidden_id)
    assert not isinstance(result, QueryExecutionResult)
    assert result.data["enemy"]["id"] == hidden_id


def test_enemy_payload_contains_linked_units(enemy_context):
    context, bundle = enemy_context

    payload = build_enemy_payload(context, bundle, bundle.enemies["enemy_1107_uoffcr"])

    assert {item["name"] for item in payload["linked_enemies"]} == {"乌萨斯平民", "斗士塔露拉"}


def test_enemy_templates_render_html_and_clean_json(enemy_context):
    context, _ = enemy_context
    result = build_enemy_query_result(context, "enemy_1009_lurker")
    assert not isinstance(result, QueryExecutionResult)
    loader = JinjaTemplateLoader(str(PROJECT_ROOT / "data" / "templates"))
    assert result.data["fallback_enemy_icon_data"].startswith("data:image/png;base64,")

    html = JinjaHtmlRenderer(loader).render("enemy", result).payload
    payload = JinjaJsonRenderer(loader).render("enemy", result).payload

    assert "潜伏者" in html
    assert '<span class="mark"><u>隐匿</u></span>' in html
    assert payload["type"] == "enemy"
    assert payload["data"]["abilities"][0]["text"] == "隐匿"
    assert "raw_text" not in payload["data"]["abilities"][0]


def test_enemy_query_returns_card_and_json_urls(enemy_context):
    context, _ = enemy_context
    calls: list[str] = []

    class FakeCardService:
        async def get(self, *, format: str, **_kwargs):
            calls.append(format)
            return SimpleNamespace(path=PROJECT_ROOT / f"artifact.{format}")

    context.card_service = FakeCardService()
    response = asyncio.run(query_enemy_by_id(context, "enemy_1007_slime")).to_response()

    assert calls == ["json", "png"]
    assert response["data"]["id"] == "enemy_1007_slime"
    assert response["card_image_url"].endswith("/artifact.png")
    assert response["data_url"].endswith("/artifact.json")


def test_unknown_enemy_id_returns_message(enemy_context):
    context, _ = enemy_context

    result = build_enemy_query_result(context, "enemy_not_exist")

    assert result.message == "未找到敌人ID: enemy_not_exist"
