from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# AI-REMOVED 2026-11-10:
# Reason: 用户仅授权结构化数据，撤回未经授权的卫戍协议查询和卡片接入。
# Trigger: 用户要求先去掉本次新增接口，后续按指导梳理添加。
# Evidence: 本次工作区 diff 中新增的卫戍协议工具、搜索和卡片代码。
# Replacement: None；仅保留 src/data/repository/bundle/autochess.py 数据结构化。
# Risk: Low；既有查询入口保持原行为。
# Human Review: Required
# Original code:
# from src.app.renderers.jinja_template_loader import JinjaTemplateLoader
# AI-REMOVED 2026-11-10:
# Reason: 用户仅授权结构化数据，撤回未经授权的卫戍协议查询和卡片接入。
# Trigger: 用户要求先去掉本次新增接口，后续按指导梳理添加。
# Evidence: 本次工作区 diff 中新增的卫戍协议工具、搜索和卡片代码。
# Replacement: None；仅保留 src/data/repository/bundle/autochess.py 数据结构化。
# Risk: Low；既有查询入口保持原行为。
# Human Review: Required
# Original code:
# from src.app.services.autochess_queries import query_autochess_detail
from src.app.services.operator_queries import resolve_search_items_by_ids, search
# AI-REMOVED 2026-11-10:
# Reason: 用户仅授权结构化数据，撤回未经授权的卫戍协议查询和卡片接入。
# Trigger: 用户要求先去掉本次新增接口，后续按指导梳理添加。
# Evidence: 本次工作区 diff 中新增的卫戍协议工具、搜索和卡片代码。
# Replacement: None；仅保留 src/data/repository/bundle/autochess.py 数据结构化。
# Risk: Low；既有查询入口保持原行为。
# Human Review: Required
# Original code:
# from src.app.services.search_card import build_search_selection_query_result
from src.data.repository.bundle.autochess import build_autochess_entries, clean_autochess_text

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def data():
    config = {
        "modeDataDict": {"normal": {"name": "标准模拟", "activeBondIdList": ["yan"]},
                         "tutorial": {"name": "入门协议", "activeBondIdList": ["yan"]}},
        "bondInfoDict": {"yan": {"name": "炎", "desc": "提升攻击力\\n<在场<@ba.vup>6</>名干员>召唤炎佑", "activeCount": 3}},
        "charShopChessDatas": {"pawn": {"charId": "operator", "goldenChessId": "gold", "chessLevel": 2},
                               "diy": {"chessType": "DIY", "charId": "operator"}},
        "charChessDataDict": {
            "pawn": {"isGolden": False, "bondIds": ["yan"], "garrisonIds": ["price"], "desc": "购买价格为<@ba.vup>1</>"},
            "gold": {"isGolden": True, "bondIds": ["yan"], "garrisonIds": ["gain"], "desc": "<获得时>层数+2"},
            "diy": {"bondIds": ["yan"]},
        },
        "shopCharChessInfoData": {"2": [{"isGolden": False, "purchasePrice": 2, "chessSoldPrice": 1},
                                           {"isGolden": True, "purchasePrice": 2, "chessSoldPrice": 1}]},
        "garrisonDataDict": {"price": {"eventType": "SERVER_PRICE", "garrisonDesc": "购买价格为1", "blackboard": [{"key": "price", "value": 9}]},
                             "gain": {"eventType": "SERVER_GAIN", "garrisonDesc": "<获得时>层数+2"}},
        "bandDataListDict": {"band": {"bandDesc": "【策略】\\n<在场6名干员>效果替换", "effectId": "effect", "inactiveModeIdList": ["normal"]}},
        "effectInfoDataDict": {"effect": {"effectName": "策略"}},
        "skillInfoDataDict": {"effect": {"bandId": "band", "skillDesc": "被动继承资金", "skillType": "PASSIVE"},
                              "upgrade": {"bandId": "band", "skillDesc": "主动选择地块", "skillType": "ACTIVE"}},
    }
    training = deepcopy(config)
    training["trainingConstData"] = {"trainingModeId": "tutorial", "trBondIds": [], "trBannedBondIds": ["yan"]}
    training["charChessDataDict"]["pawn"]["desc"] = "教程效果"
    config["trainingData"] = training
    later = deepcopy(config)
    later["charChessDataDict"]["pawn"]["desc"] = "下期效果"
    return {"gamedata": {"character_table": {"operator": {"name": "真理"}}, "activity_table": {
        "activity": {"AUTOCHESS": {"act": {"v1": config, "v2": later}}},
        "basicInfo": {"act": {"name": "卫戍协议:规程"}},
        "autoChessData": {"bandDataDict": {"band": {"bandName": "策略角色"}}},
    }}}


def make_context(data):
    entries, aliases = build_autochess_entries(data)
    bundle = SimpleNamespace(
        autochess_entries=entries, autochess_alias_to_ids=aliases,
        operators={}, operator_name_to_id={}, token_name_to_id={}, skin_name_to_id={},
        material_name_to_id={}, stage_alias_to_ids={}, enemy_alias_to_ids={}, tokens={},
        version="test", resource_root=ROOT / "resources",
    )
    return SimpleNamespace(
        data_repository=SimpleNamespace(get_bundle=lambda: bundle),
        cfg=SimpleNamespace(ProjectRoot=ROOT, ResourcePath=ROOT / "resources", BaseUrl="https://example.test"),
        card_service=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(path=Path("/tmp/card.png")))),
        prefer_local_artifact_path=True,
    ), bundle


def test_text_preserves_conditions_and_escapes():
    assert clean_autochess_text("<获得时><@ba.vup>+1</>\\n<在场<@ba.vup>6</>名干员>") == "<获得时>+1\n<在场6名干员>"
    assert clean_autochess_text(None) == ""


def test_versions_training_variants_and_prices_are_independent(data):
    entries, _ = build_autochess_entries(data)
    first = entries["autochess:act:v1:standard:chess:pawn"]
    assert first["variants"][0]["purchase_price"] == 2
    assert first["variants"][0]["description"] == "购买价格为1"
    assert first["variants"][1]["traits"][0]["trigger"] == "SERVER_GAIN"
    assert first["variants"][1]["description"] == "<获得时>层数+2"
    assert entries["autochess:act:v2:standard:chess:pawn"]["variants"][0]["description"] == "下期效果"
    assert entries["autochess:act:v1:training:chess:pawn"]["variants"][0]["description"] == "教程效果"
    assert first["modes"][0]["id"] == "normal"
    tutorial = entries["autochess:act:v1:training:bond:yan"]
    assert tutorial["modes"][0]["inactive_bond_ids"] == ["yan"]
    assert len(tutorial["members"]) == 1
    assert not any(eid.endswith(":diy") for eid in entries)


def test_strategy_preserves_overview_and_all_skill_types(data):
    entries, aliases = build_autochess_entries(data)
    entry = entries["autochess:act:v1:standard:strategy:band"]
    assert "<在场6名干员>效果替换" in entry["description"]
    assert [skill["type"] for skill in entry["skills"]] == ["PASSIVE", "ACTIVE"]
    assert entry["id"] in aliases["策略角色"]


def test_missing_traits_and_prices_do_not_invent_values(data):
    config = data["gamedata"]["activity_table"]["activity"]["AUTOCHESS"]["act"]["v1"]
    config["shopCharChessInfoData"] = {}
    config["charChessDataDict"]["pawn"]["garrisonIds"] = None
    entries, _ = build_autochess_entries(data)
    variant = entries["autochess:act:v1:standard:chess:pawn"]["variants"][0]
    assert variant["purchase_price"] is None
    assert variant["traits"] == []
    assert build_autochess_entries({}) == ({}, {})


def test_structured_data_is_not_exposed_by_search(data):
    from src.helpers.gamedata.search import build_sources

    context, bundle = make_context(data)
    assert bundle.autochess_entries
    assert "autochess" not in {source.key for source in build_sources(bundle)}
    assert search(context, "卫戍协议真理").data is None
    with pytest.raises(ValueError, match="未找到可组装"):
        resolve_search_items_by_ids(bundle, [next(iter(bundle.autochess_entries))])


def test_mcp_has_no_autochess_tool_or_instructions(tmp_path):
    from fastapi import FastAPI
    from src.adapters.mcp.app import register_asgi, server_instructions
    from src.app.config import Config

    mcp = register_asgi(FastAPI(), Config(ProjectRoot=ROOT, ResourcePath=tmp_path))
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 17
    assert "get_autochess_detail" not in {tool.name for tool in tools}
    assert "get_autochess_bond_detail" in server_instructions
    assert all("卫戍协议" not in (tool.description or "") for tool in tools
               if tool.name not in {"get_operator_basic_data", "search", "get_autochess_bond_detail", "get_autochess_strategy_detail"})


def card_bundle(data):
    _, bundle = make_context(data)
    bundle.tables = data
    data["gamedata"]["activity_table"]["autoChessData"]["versionInfoDict"] = {
        "v1": {"activityId": "act", "versionId": "v1", "startTime": 1, "endTime": 100},
        "v2": {"activityId": "act", "versionId": "v2", "startTime": 100, "endTime": 200},
    }
    return bundle


def test_operator_card_uses_only_current_chess_and_full_traits(data):
    from datetime import datetime, timezone
    from src.domain.services.operator_autochess import build_operator_autochess

    bundle = card_bundle(data)
    now = datetime.fromtimestamp(50, timezone.utc)
    info = build_operator_autochess(bundle, "operator", ROOT, now=now)
    assert info["title"] == "卫戍协议：规程 棋子信息"
    assert info["variants"][0]["description"] == "购买价格为1"
    assert info["variants"][0]["price"] == 2
    assert info["variants"][1]["description"] == "<获得时>层数+2"
    assert [b["name"] for b in info["bonds"]] == ["炎"]
    assert info["coin_icon"].startswith("data:image/png;base64,")
    assert "ruleset" not in info and "version_id" not in info
    assert build_operator_autochess(bundle, "missing", ROOT, now=now) is None
    assert build_operator_autochess(bundle, "operator", ROOT, now=datetime.fromtimestamp(201, timezone.utc)) is None
    # 新档期没有该干员时，不得把旧档期棋子资料带入角色卡。
    bundle.autochess_entries = {k: v for k, v in bundle.autochess_entries.items() if v["version_id"] == "v1"}
    assert build_operator_autochess(bundle, "operator", ROOT, now=datetime.fromtimestamp(150, timezone.utc)) is None


def test_operator_card_merges_identical_traits_and_omits_empty_panel(data):
    from datetime import datetime, timezone
    from src.domain.services.operator_autochess import build_operator_autochess

    bundle = card_bundle(data)
    now = datetime.fromtimestamp(50, timezone.utc)
    entry = bundle.autochess_entries["autochess:act:v1:standard:chess:pawn"]
    entry["variants"][1] = {**deepcopy(entry["variants"][0]), "name": "精锐"}
    assert build_operator_autochess(bundle, "operator", ROOT, now=now)["variants"][0]["name"] == "普通 / 精锐"
    for variant in entry["variants"]:
        variant["description"] = ""
        variant["traits"] = []
    assert build_operator_autochess(bundle, "operator", ROOT, now=now) is None


def test_card_prefers_complete_display_text_over_overlapping_event_text(data):
    from datetime import datetime, timezone
    from src.domain.services.operator_autochess import build_operator_autochess

    bundle = card_bundle(data)
    variant = bundle.autochess_entries["autochess:act:v1:standard:chess:pawn"]["variants"][0]
    variant["description"] = "<战斗中>弱点伤害；\n每击倒一名敌人，盟约层数+2"
    variant["traits"] = [{"description": "<战斗中>每击倒一名敌人，盟约层数+2"}]
    result = build_operator_autochess(bundle, "operator", ROOT, now=datetime.fromtimestamp(50, timezone.utc))
    assert result["variants"][0]["description"] == variant["description"]


# AI-REMOVED 2026-11-10:
# Reason: 用户仅授权结构化数据，撤回未经授权的卫戍协议查询和卡片接入。
# Trigger: 用户要求先去掉本次新增接口，后续按指导梳理添加。
# Evidence: 本次工作区 diff 中新增的卫戍协议工具、搜索和卡片代码。
# Replacement: None；仅保留 src/data/repository/bundle/autochess.py 数据结构化。
# Risk: Low；既有查询入口保持原行为。
# Human Review: Required
# Original code:
# def test_search_and_selection_keep_scope(data):
#     context, bundle = make_context(data)
#     found = search(context, "卫戍协议真理").data["items"]
#     assert len(found) == 4
#     assert all(item["type"] == "卫戍协议棋子" for item in found)
#     assert {item["version_id"] for item in found} == {"v1", "v2"}
#     selected = resolve_search_items_by_ids(bundle, [found[2]["id"], found[0]["id"]])
#     card, _ = build_search_selection_query_result(context, selected)
#     assert card.data["groups"][0]["items"][0]["id"] == found[2]["id"]
#     assert "v2" in card.data["groups"][0]["items"][0]["meta"]


# AI-REMOVED 2026-11-10:
# Reason: 用户仅授权结构化数据，撤回未经授权的卫戍协议查询和卡片接入。
# Trigger: 用户要求先去掉本次新增接口，后续按指导梳理添加。
# Evidence: 本次工作区 diff 中新增的卫戍协议工具、搜索和卡片代码。
# Replacement: None；仅保留 src/data/repository/bundle/autochess.py 数据结构化。
# Risk: Low；既有查询入口保持原行为。
# Human Review: Required
# Original code:
# def test_details_cards_and_render_failure(data):
#     context, bundle = make_context(data)
#     entry_id = "autochess:act:v1:standard:chess:pawn"
#     response = asyncio.run(query_autochess_detail(context, entry_id)).to_response()
#     assert response["card_image_url"].startswith("https://example.test/cards/autochess/")
#     assert response["data_url"].endswith("artifact.json")
#     assert response["image_path"] == "/tmp/card.png"
#     response["data"]["name"] = "changed"
#     assert bundle.autochess_entries[entry_id]["name"] == "真理"
#     context.card_service.get.side_effect = RuntimeError("renderer unavailable")
#     failed = asyncio.run(query_autochess_detail(context, entry_id)).to_response()
#     assert "data" in failed and "card_image_url" not in failed
#     assert asyncio.run(query_autochess_detail(context, " ")).message == "entry_id 不能为空"
#     assert "未找到" in asyncio.run(query_autochess_detail(context, "真理")).message


# AI-REMOVED 2026-11-10:
# Reason: 用户仅授权结构化数据，撤回未经授权的卫戍协议查询和卡片接入。
# Trigger: 用户要求先去掉本次新增接口，后续按指导梳理添加。
# Evidence: 本次工作区 diff 中新增的卫戍协议工具、搜索和卡片代码。
# Replacement: None；仅保留 src/data/repository/bundle/autochess.py 数据结构化。
# Risk: Low；既有查询入口保持原行为。
# Human Review: Required
# Original code:
# def test_template_keeps_angle_bracket_conditions_visible(data):
#     entries, _ = build_autochess_entries(data)
#     loader = JinjaTemplateLoader(str(ROOT / "data/templates"))
#     for kind, source in [("chess", "pawn"), ("bond", "yan"), ("strategy", "band")]:
#         entry = entries[f"autochess:act:v1:standard:{kind}:{source}"]
#         html = loader.render_by_kind(kind="html", template_name="autochess", ext="html", ctx={"entry": entry})
#         assert "&lt;" in html
#         assert "<获得时>" not in html
#         assert "<@" not in html


# AI-REMOVED 2026-11-10:
# Reason: 用户仅授权结构化数据，撤回未经授权的卫戍协议查询和卡片接入。
# Trigger: 用户要求先去掉本次新增接口，后续按指导梳理添加。
# Evidence: 本次工作区 diff 中新增的卫戍协议工具、搜索和卡片代码。
# Replacement: None；仅保留 src/data/repository/bundle/autochess.py 数据结构化。
# Risk: Low；既有查询入口保持原行为。
# Human Review: Required
# Original code:
# def test_mcp_registration_and_not_ready():
#     from src.adapters.mcp.mcp_tools.autochess import register_autochess_tool
#     registered = {}
#
#     class MCP:
#         def tool(self, **kwargs):
#             def register(fn):
#                 registered[fn.__name__] = fn
#                 return fn
#             return register
#
#     register_autochess_tool(MCP(), SimpleNamespace(state=SimpleNamespace()))
#     assert asyncio.run(registered["get_autochess_detail"]("id")) == {"message": "未初始化数据上下文"}


def test_current_bond_search_and_members(data, monkeypatch):
    from datetime import datetime, timezone
    from src.domain.services import autochess_bond
    from src.app.services.operator_queries import _build_search_items
    from src.helpers.gamedata.search import build_sources, search_source_spec

    bundle = card_bundle(data)
    now = datetime.fromtimestamp(50, timezone.utc)
    bonds = autochess_bond.current_bonds(bundle, now=now)
    assert len(bonds) == 1
    entry = next(iter(bonds.values()))
    detail = autochess_bond.bond_detail(bundle, entry)
    assert len(detail['所属棋子']) == 1
    assert detail['所属棋子'][0]['名称'] == '真理'
    assert detail['效果'] == entry['description']
    assert not autochess_bond.current_bonds(bundle, now=datetime.fromtimestamp(201, timezone.utc))
    monkeypatch.setattr(autochess_bond, 'current_autochess_version', lambda *args, **kwargs: {
        'activityId': 'act', 'versionId': 'v1'})
    sources = build_sources(bundle, source_key=['autochess_bond'])
    for query in [entry['name'], '卫戍协议 ' + entry['name']]:
        matches = search_source_spec(query, sources=sources).matches
        items = _build_search_items(matches, {})
        assert [i['id'] for i in items] == [entry['id']]
        assert 'ruleset' not in items[0] and 'version_id' not in items[0]
    assert resolve_search_items_by_ids(bundle, [entry['id']])[0]['type'] == '卫戍协议盟约'
    invalid = entry['id'].replace(':standard:', ':training:')
    with pytest.raises(ValueError):
        resolve_search_items_by_ids(bundle, [invalid])


def test_bond_detail_invalid_id_does_not_render(data):
    from src.app.services.autochess_bond_queries import query_autochess_bond_detail
    context, _ = make_context(data)
    result = asyncio.run(query_autochess_bond_detail(context, 'missing'))
    assert result.data is None
    assert '未找到当期盟约' in result.message


def test_strategy_search_current_scope_and_unlock(data, monkeypatch):
    from src.domain.services import autochess_strategy
    from src.helpers.gamedata.search import build_sources, search_source_spec
    from src.app.services.operator_queries import _build_search_items
    bundle = card_bundle(data)
    monkeypatch.setattr(autochess_strategy, 'current_autochess_version', lambda *a, **k: {'activityId': 'act', 'versionId': 'v1'})
    entries = autochess_strategy.current_strategies(bundle)
    assert len(entries) == 1
    entry = next(iter(entries.values()))
    entry['unlock_description'] = '累计消耗100资金解锁'
    detail = autochess_strategy.strategy_detail(entry)
    assert detail['解锁条件'] == '累计消耗100资金解锁'
    assert {s['类型'] for s in detail['技能']} == {'主动', '被动'}
    sources = build_sources(bundle, source_key=['autochess_strategy'])
    for query in [entry['name'], entry['owner_name'], '卫戍协议 ' + entry['name']]:
        items = _build_search_items(search_source_spec(query, sources=sources).matches, {})
        assert [i['id'] for i in items] == [entry['id']]
        assert 'ruleset' not in items[0]
    assert resolve_search_items_by_ids(bundle, [entry['id']])[0]['type'] == '卫戍协议策略'
    with pytest.raises(ValueError):
        resolve_search_items_by_ids(bundle, [entry['id'].replace(':v1:', ':v2:')])
    entry['unlock_description'] = ''
    assert autochess_strategy.strategy_detail(entry)['解锁条件'] == '暂无解锁条件说明'


def test_strategy_limits_preserve_zero_cost_and_do_not_guess_cooldown():
    from src.domain.services.autochess_strategy import strategy_detail
    entry = {'id': 's', 'name': '策略', 'activity_name': '卫戍协议:规程', 'skills': [
        {'type': 'ACTIVE', 'description': '效果', 'cost': 0, 'usage_type': 'ROUND_RESET', 'usage_count': 2},
        {'type': 'ACTIVE', 'description': '冷却效果', 'cost': 1, 'usage_type': 'COOLDOWN', 'usage_count': 3},
        {'type': 'NONE', 'description': '解锁状态'}]}
    skills = strategy_detail(entry)['技能']
    assert skills[0]['费用'] == 0 and skills[0]['使用限制'] == '每回合限2次'
    assert '使用限制' not in skills[1]
    assert skills[2]['类型'] == '状态说明'


def test_strategy_render_failure_keeps_unlock_and_full_text(data, monkeypatch):
    from src.app.services import autochess_strategy_queries as queries
    from src.domain.services.autochess_strategy import current_strategies
    from src.domain.services import autochess_strategy
    context, bundle = make_context(data)
    monkeypatch.setattr(autochess_strategy, 'current_autochess_version', lambda *a, **k: {'activityId': 'act', 'versionId': 'v1'})
    entry = next(iter(current_strategies(bundle).values()))
    context.cfg = SimpleNamespace(ProjectRoot=ROOT, BaseUrl=None)
    context.card_service = SimpleNamespace(get=AsyncMock(side_effect=RuntimeError('render failed')))
    result = asyncio.run(queries.query_autochess_strategy_detail(context, entry['id']))
    assert result.data['说明'] == entry['description']
    assert result.data['解锁条件']
    assert '卡片生成失败' in result.message
    assert asyncio.run(queries.query_autochess_strategy_detail(context, 'invalid')).data is None


def test_strategy_display_merges_repeated_effect_without_losing_conditions():
    from src.domain.services.autochess_strategy import strategy_display
    detail = {'说明': '【策略】\n在场6人时解锁\n拖拽使用（消耗1）：效果', '技能': [
        {'类型': '状态说明', '描述': '【策略-未解锁】\n在场6人时解锁\n拖拽使用：效果'},
        {'类型': '主动', '描述': '【策略】\n拖拽使用：效果', '费用': 1}]}
    overview, skills = strategy_display(detail)
    assert not overview and len(skills) == 1
    assert skills[0]['描述'] == detail['说明'] and skills[0]['费用'] == 1
    assert len(detail['技能']) == 2
    detail['技能'][0]['描述'] += '\n独有条件'
    assert len(strategy_display(detail)[1]) == 2
