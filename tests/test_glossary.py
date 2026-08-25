import json
from pathlib import Path
from types import SimpleNamespace

from src.app.services.glossary_queries import query_glossary
from src.helpers.glossary import mark_glossary_used_terms


def _context(glossary: dict[str, str]) -> SimpleNamespace:
    bundle = SimpleNamespace(tables={"local_glossary": glossary})
    repository = SimpleNamespace(get_bundle=lambda: bundle)
    return SimpleNamespace(data_repository=repository)


def _local_glossary() -> dict[str, str]:
    glossary_path = Path(__file__).parents[1] / "data" / "local" / "glossary.json"
    return json.loads(glossary_path.read_text(encoding="utf-8"))


def test_query_glossary_matches_latin_terms_case_insensitively() -> None:
    context = _context({"DPS": "每秒伤害", "攻击间隔": "每X秒攻击一次"})

    assert query_glossary(context, "dps")["DPS"] == "每秒伤害"
    assert query_glossary(context, "DPS")["DPS"] == "每秒伤害"


def test_query_glossary_matches_explanation_text() -> None:
    context = _context({"攻击力": "决定造成伤害的基础数值", "生命值": "决定可承受的伤害量"})

    assert query_glossary(context, "基础数值") == {"攻击力": "决定造成伤害的基础数值"}


def test_query_glossary_prefers_name_matches_over_explanation_matches() -> None:
    context = _context({"攻击力": "决定基础数值", "DPS": "根据攻击力计算"})

    assert query_glossary(context, "攻击力") == {"攻击力": "决定基础数值"}


def test_query_glossary_matches_terms_contained_in_longer_queries() -> None:
    context = _context({"攻击力": "决定基础数值"})

    assert query_glossary(context, "干员攻击力") == {"攻击力": "决定基础数值"}


def test_query_glossary_cascades_transitively() -> None:
    context = _context(
        {
            "DPS": "由总伤和攻击间隔计算",
            "总伤": "统计期内的累计值",
            "攻击间隔": "由攻击速度换算",
            "攻击速度": "影响攻击频率",
        }
    )

    assert query_glossary(context, "DPS") == {
        "DPS": "由总伤和攻击间隔计算",
        "总伤": "统计期内的累计值",
        "攻击间隔": "由攻击速度换算",
        "攻击速度": "影响攻击频率",
    }


def test_query_glossary_does_not_search_explanations_after_name_match() -> None:
    context = _context(
        {
            "物理伤害": "物理类结算",
            "法术伤害": "法术类结算",
            "DPS": "每秒伤害",
        }
    )

    assert query_glossary(context, "伤害") == {
        "物理伤害": "物理类结算",
        "法术伤害": "法术类结算",
    }


def test_query_glossary_uses_explanations_for_aliases() -> None:
    context = _context({"法术抗性": "常简称法抗，也可能写作魔法抗性"})

    assert query_glossary(context, "法抗") == {
        "法术抗性": "常简称法抗，也可能写作魔法抗性"
    }
    assert query_glossary(context, "魔法抗性") == {
        "法术抗性": "常简称法抗，也可能写作魔法抗性"
    }


def test_local_glossary_has_bounded_cascades() -> None:
    glossary = _local_glossary()
    context = _context(glossary)

    assert {"伤害", "法抗", "术师"}.isdisjoint(glossary)
    assert set(query_glossary(context, "攻击力")) == {"攻击力"}
    assert set(query_glossary(context, "伤害")) == {
        "攻击力",
        "物理伤害",
        "法术伤害",
        "真实伤害",
        "防御力",
        "法术抗性",
        "物理穿透",
        "法术穿透",
    }
    assert set(query_glossary(context, "DPS")) == set(glossary) - {"技力", "专精"}


def test_local_glossary_explains_mastery_levels_and_unlocks() -> None:
    glossary = _local_glossary()

    mastery = glossary["专精"]
    assert "专精一、专精二、专精三" in mastery
    assert "解包技能等级8、9、10" in mastery
    assert "精英二" in mastery
    assert "1~7级进度共用" in mastery


def test_local_glossary_keeps_top_level_explanations_concise() -> None:
    glossary = _local_glossary()

    assert len(glossary["DPS"]) < 200
    assert len(glossary["攻击间隔"]) < 150


def test_mark_glossary_matches_latin_terms_case_insensitively() -> None:
    context = _context({"DPS": "每秒伤害", "攻击间隔": "每X秒攻击一次"})

    assert set(mark_glossary_used_terms(context, "这里比较dps和攻击间隔")) == {"DPS", "攻击间隔"}
