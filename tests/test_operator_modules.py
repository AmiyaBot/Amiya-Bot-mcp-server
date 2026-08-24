import asyncio
from pathlib import Path
from types import SimpleNamespace

from src.app.config import Config
from src.app.renderers.jinja_html_renderer import JinjaHtmlRenderer
from src.app.renderers.jinja_template_loader import JinjaTemplateLoader
from src.app.services.operator_module_output import build_operator_module_payload
from src.app.services.operator_queries import query_operator_modules_by_id
from src.data.repository.bundle.bundle_builder import load_bundle_from_disk
from src.domain.services.operator_module import build_operator_module_query_result


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _build_context():
    cfg = Config(
        ProjectRoot=PROJECT_ROOT,
        ResourcePath=PROJECT_ROOT / "resources",
        GameDataRepo="local-test",
        BaseUrl="https://example.test",
    )
    bundle = load_bundle_from_disk(cfg, version="test")
    repository = SimpleNamespace(get_bundle=lambda: bundle)
    return SimpleNamespace(cfg=cfg, data_repository=repository), bundle


def test_build_silverash_module_payload_contains_complete_levels():
    context, bundle = _build_context()
    operator = bundle.operators["char_172_svrash"]

    result = build_operator_module_query_result(context, operator)
    payload = build_operator_module_payload(result)

    assert payload["干员"]["中文名"] == "银灰"
    assert len(payload["模组"]) == 2

    initial, advanced = payload["模组"]
    assert initial["名称"] == "银灰证章"
    assert "等级数据" not in initial

    assert advanced["名称"] == "雪境羽兽护理套组"
    assert advanced["类型"]["代码"] == "LOR-X"
    assert advanced["解锁条件"]["精英阶段"] == "精英二"
    assert advanced["解锁条件"]["等级"] == 60
    assert advanced["解锁条件"]["信赖"] == 0
    assert len(advanced["解锁条件"]["任务"]) == 2

    levels = advanced["等级数据"]
    assert [item["等级"] for item in levels] == [1, 2, 3]
    assert [item["信赖要求"] for item in levels] == [0, 50, 100]
    assert {item["属性"]: item["数值"] for item in levels[0]["属性提升"]} == {
        "最大生命值": 190,
        "攻击力": 45,
    }
    assert "10%" in levels[0]["分支特性更新"][0]["描述"]
    assert any(item["名称"] == "模组数据块" for item in levels[0]["升级材料"])
    assert any(item.get("名称") == "领袖" for item in levels[1]["天赋更新"])


def test_module_payload_includes_token_attribute_updates():
    context, bundle = _build_context()
    operator = bundle.operators["char_2023_ling"]

    result = build_operator_module_query_result(context, operator)
    payload = build_operator_module_payload(result)

    token_updates = [
        update
        for module in payload["模组"]
        for level in module.get("等级数据", [])
        for update in level.get("召唤物属性提升", [])
    ]
    assert token_updates
    assert all(item.get("召唤物id") for item in token_updates)
    assert any(item.get("属性提升") for item in token_updates)


def test_operator_module_template_renders_reference_sections():
    context, bundle = _build_context()
    operator = bundle.operators["char_172_svrash"]
    result = build_operator_module_query_result(context, operator)
    renderer = JinjaHtmlRenderer(
        JinjaTemplateLoader(str(PROJECT_ROOT / "data" / "templates"))
    )

    html = renderer.render("operator_module", result).payload

    assert "银灰 的模组" in html
    assert "雪境羽兽护理套组" in html
    assert "解锁条件" in html
    assert "基础属性更新" in html
    assert "分支特性更新" in html
    assert "升级材料消耗" in html
    assert "升级要求 · 信赖 50%" in html
    assert "升级要求 · 信赖 100%" in html
    assert "信赖值 <span class=\"mark\">100%</span>" not in html


def test_query_operator_modules_handles_missing_module_and_invalid_id():
    context, _ = _build_context()

    no_module = asyncio.run(query_operator_modules_by_id(context, "char_009_12fce"))
    invalid = asyncio.run(query_operator_modules_by_id(context, "char_invalid"))

    assert no_module.message == "干员 12F 尚未拥有模组"
    assert invalid.message == "未找到干员ID: char_invalid"
