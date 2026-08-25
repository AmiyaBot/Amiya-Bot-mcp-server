from pathlib import Path

from src.app.config import Config
from src.app.services.operator_output import build_operator_payload
from src.data.repository.bundle.bundle_builder import load_bundle_from_disk
from src.domain.types import QueryResult
from src.helpers.bundle import parse_template


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_parse_template_preserves_fractional_values() -> None:
    blackboard = [
        {"key": "atk", "value": 0.45, "valueStr": None},
        {"key": "stun", "value": 0.4, "valueStr": None},
        {"key": "scale", "value": 1.75, "valueStr": None},
    ]

    description = "攻击力+{atk:0%}，倍率{scale:0%}，晕眩{stun}秒"

    assert parse_template(blackboard, description) == "攻击力+45%，倍率175%，晕眩0.4秒"


def test_parse_template_supports_decimal_format_specs_and_string_values() -> None:
    blackboard = [
        {"key": "probability", "value": 0.125, "valueStr": None},
        {"key": "duration", "value": 1.25, "valueStr": None},
        {"key": "range_id", "value": 0.0, "valueStr": "3-7"},
    ]

    description = "概率{probability:0.0%}，持续{duration:0.0}秒，范围{range_id}"

    assert parse_template(blackboard, description) == "概率12.5%，持续1.2秒，范围3-7"


def test_typhon_skill_descriptions_keep_the_original_multipliers() -> None:
    cfg = Config(
        ProjectRoot=PROJECT_ROOT,
        ResourcePath=PROJECT_ROOT / "resources",
        GameDataRepo="local-test",
        BaseUrl="https://example.test",
    )
    bundle = load_bundle_from_disk(cfg, version="test")
    typhon = bundle.operators["char_2012_typhon"]

    first, second, third = [skill.levels[-1].description for skill in typhon.skills]

    assert "攻击力+45%" in first
    assert "攻击力+50%" in second
    assert "40%概率晕眩目标1秒" in second
    assert "攻击力175%的物理伤害" in third
    assert "晕眩0.4秒" in third

    mcp_payload = build_operator_payload(
        QueryResult(
            type="operator_profile",
            key=typhon.name,
            title=typhon.name,
            data={"op": typhon},
        )
    )
    mcp_descriptions = [skill["描述"] for skill in mcp_payload["技能"]]

    assert "攻击力+45%" in mcp_descriptions[0]
    assert "攻击力+50%" in mcp_descriptions[1]
    assert "40%概率晕眩目标1秒" in mcp_descriptions[1]
    assert "攻击力175%的物理伤害" in mcp_descriptions[2]
    assert "晕眩0.4秒" in mcp_descriptions[2]
