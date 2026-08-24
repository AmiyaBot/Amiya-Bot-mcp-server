from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from src.app.services import operator_queries
from src.domain.models.skin import Skin


class _Artifact:
    def __init__(self, skin_id: str) -> None:
        self.url = f"https://example.test/char-skins/{skin_id}.webp"

    def to_data_uri(self) -> str:
        return "data:image/webp;base64,cHJldmlldw=="


def test_query_operator_skins_returns_selection_card_and_numbered_urls(
    monkeypatch,
    tmp_path: Path,
) -> None:
    skins = [
        Skin(
            operator_id="char_test",
            operator_name="测试干员",
            skin_id="char_test#1",
            skin_key="stage0",
            name="初始",
            is_evolve=True,
        ),
        Skin(
            operator_id="char_test",
            operator_name="测试干员",
            skin_id="char_test@skin#1",
            skin_key="skin1",
            name="测试时装",
        ),
    ]
    operator = SimpleNamespace(
        id="char_test",
        name="测试干员",
        skins=lambda: skins,
    )
    bundle = SimpleNamespace(version="bundle-v1", operators={operator.id: operator})
    context = SimpleNamespace(
        cfg=SimpleNamespace(ResourcePath=tmp_path),
        data_repository=SimpleNamespace(get_bundle=lambda: bundle),
    )

    async def fake_resolve_skin_artifact(_context, skin_id: str):
        # 即使某个皮肤立绘缺失，它也必须继续出现在选择卡和编号列表中。
        if skin_id == "char_test@skin#1":
            return None
        return _Artifact(skin_id)

    async def fake_render_skin_card(_context, _operator, skin, _artifact, **_kwargs):
        return f"https://example.test/cards/{skin.skin_id}.png"

    captured_selection_items: list[dict] = []

    async def fake_render_selection_card(
        _context,
        _operator,
        selection_items: list[dict],
        _bundle_version: str,
    ) -> str:
        captured_selection_items.extend(selection_items)
        return "https://example.test/cards/skin-selection.png"

    monkeypatch.setattr(
        operator_queries,
        "resolve_skin_artifact_by_id",
        fake_resolve_skin_artifact,
    )
    monkeypatch.setattr(
        operator_queries,
        "_render_operator_skin_card",
        fake_render_skin_card,
    )
    monkeypatch.setattr(
        operator_queries,
        "_render_operator_skin_selection_card",
        fake_render_selection_card,
    )

    result = asyncio.run(operator_queries.query_operator_skins(context, operator.id))
    response = result.to_response()

    assert response["card_image_url"] == "https://example.test/cards/skin-selection.png"
    assert response["data"]["selection_card_url"] == response["card_image_url"]
    assert [item["序号"] for item in response["data"]["skins"]] == [1, 2]
    assert response["data"]["skins"][0]["card_url"].endswith("char_test#1.png")
    assert response["data"]["skins"][0]["立绘URL"].endswith("char_test#1.webp")
    assert response["data"]["skins"][1]["card_url"] == ""
    assert response["data"]["skins"][1]["立绘URL"] == ""
    assert [item["index"] for item in captured_selection_items] == [1, 2]
