from functools import lru_cache
from pathlib import Path

from src.app.config import Config
from src.app.services.operator_output import build_operator_payload, build_operator_skill_payload
from src.data.repository.bundle.bundle_builder import load_bundle_from_disk
from src.domain.types import QueryResult
from src.helpers.bundle import get_table


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def _bundle():
    cfg = Config(
        ProjectRoot=PROJECT_ROOT,
        ResourcePath=PROJECT_ROOT / "resources",
        GameDataRepo="local-test",
        BaseUrl="https://example.test",
    )
    return load_bundle_from_disk(cfg, version="test")


def _skill_payload(operator_id: str) -> dict:
    bundle = _bundle()
    return build_operator_skill_payload(
        bundle.operators[operator_id],
        sp_type_name=get_table(bundle.tables, "sp_type", source="local", default={}),
        skill_type_name=get_table(bundle.tables, "skill_type", source="local", default={}),
    )


def _basic_payload(operator_id: str) -> dict:
    operator = _bundle().operators[operator_id]
    return build_operator_payload(
        QueryResult(
            type="operator_profile",
            key=operator.name,
            title=operator.name,
            data={"op": operator},
        )
    )


def test_full_skill_payload_contains_every_skill_and_level() -> None:
    payload = _skill_payload("char_2012_typhon")

    assert payload["技能数量"] == 3
    assert [len(skill["等级"]) for skill in payload["技能"]] == [10, 10, 10]
    assert [level["游戏内等级"] for level in payload["技能"][0]["等级"]] == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "专精一",
        "专精二",
        "专精三",
    ]
    assert payload["技能"][0]["等级"][6]["升级归属"] == "干员全部技能共用"
    assert payload["技能"][0]["等级"][7]["升级归属"] == "当前技能独立专精"
    assert payload["技能"][0]["等级"][9]["专精等级"] == 3


def test_basic_payload_labels_max_level_skill_snapshot() -> None:
    six_star = _basic_payload("char_2012_typhon")
    three_star = _basic_payload("char_123_fang")

    assert "专精三数据" in six_star["技能数据说明"]
    assert {skill["游戏内等级"] for skill in six_star["技能"]} == {"专精三"}
    assert "3星干员" in three_star["技能数据说明"]
    assert three_star["技能"][0]["游戏内等级"] == "7"


def test_operator_without_skills_returns_an_empty_complete_list() -> None:
    payload = _skill_payload("char_285_medic2")

    assert payload["技能数量"] == 0
    assert payload["技能"] == []
    assert payload["说明"] == "该干员没有技能。"
