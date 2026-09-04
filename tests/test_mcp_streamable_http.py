from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from mcp.types import LATEST_PROTOCOL_VERSION

from src.adapters.mcp.app import register_asgi
from src.app.config import Config
from src.app.services.recruit_queries import _normalize_tags
from src.app.services.recruit_queries import query_recruit


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _sse_json(response: httpx.Response) -> dict:
    data_lines = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert data_lines, response.text
    return json.loads("\n".join(data_lines))


def test_normalize_recruit_tags_keeps_all_screenshot_tags_in_input_order() -> None:
    known_tags = {
        "高级资深干员",
        "近卫干员",
        "输出",
        "近战位",
        "支援",
    }
    screenshot_tags = [
        "高级资深干员",
        "近卫干员",
        "输出",
        "近战位",
        "支援",
    ]

    tags, max_rarity = _normalize_tags(screenshot_tags, known_tags)

    assert tags == screenshot_tags
    assert max_rarity == 6


def test_normalize_recruit_tags_ignores_unknown_values_and_deduplicates() -> None:
    tags, max_rarity = _normalize_tags(
        ["近卫干员", "未知词条", "近卫干员", "输出"],
        {"近卫干员", "输出"},
    )

    assert tags == ["近卫干员", "输出"]
    assert max_rarity == 5


async def test_recruit_response_excludes_render_only_base64(tmp_path: Path) -> None:
    portrait = tmp_path / "assets" / "portrait" / "char_test#1.png"
    portrait.parent.mkdir(parents=True)
    portrait.write_bytes(b"test-portrait")

    operator = SimpleNamespace(
        id="char_test",
        name="测试干员",
        rarity=5,
        tags=["近卫干员", "输出", "近战位"],
        is_recruit=True,
    )
    bundle = SimpleNamespace(
        version="test-bundle",
        operators={operator.id: operator},
    )

    class CardService:
        payload = None

        async def get(self, **kwargs):
            self.payload = kwargs["payload"]
            return SimpleNamespace()

    card_service = CardService()
    context = SimpleNamespace(
        cfg=SimpleNamespace(
            ResourcePath=tmp_path,
            BaseUrl="https://example.test/",
        ),
        data_repository=SimpleNamespace(get_bundle=lambda: bundle),
        card_service=card_service,
    )

    response = await query_recruit(
        context,
        ["近卫干员", "输出", "近战位"],
    )

    assert response["card_image_url"].startswith("https://example.test/cards/")
    response_operators = [
        item
        for group in response["groups"]
        for item in group["operators"]
    ]
    assert response_operators
    assert all("image_data" not in item for item in response_operators)

    render_operators = [
        item
        for group in card_service.payload.data["groups"]
        for item in group["operators"]
    ]
    assert render_operators
    assert all(
        item["image_data"].startswith("data:image/png;base64,")
        for item in render_operators
    )


async def test_streamable_http_initialize_and_list_tools(tmp_path: Path) -> None:
    app = FastAPI()
    cfg = Config(
        ProjectRoot=tmp_path,
        ResourcePath=tmp_path / "resources",
        BaseUrl="http://testserver/",
        McpDnsRebindingProtectionEnabled=False,
    )
    mcp = register_asgi(app, cfg)

    transport = httpx.ASGITransport(app=app)
    common_headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    async with mcp.session_manager.run():
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            legacy_sse_response = await client.get(
                "/mcp/sse",
                follow_redirects=False,
            )
            assert legacy_sse_response.status_code == 307
            assert legacy_sse_response.headers["location"] == "/mcp/sse/"

            initialize_response = await client.post(
                "/mcp",
                headers=common_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": LATEST_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "pytest", "version": "1.0"},
                    },
                },
            )

            assert initialize_response.status_code == 200
            assert _sse_json(initialize_response)["result"]["serverInfo"]["name"] == "明日方舟知识库"
            assert "Mcp-Session-Id" not in initialize_response.headers

            request_headers = {
                **common_headers,
                "Mcp-Protocol-Version": LATEST_PROTOCOL_VERSION,
            }

            initialized_response = await client.post(
                "/mcp",
                headers=request_headers,
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                },
            )
            assert initialized_response.status_code == 202

            tools_response = await client.post(
                "/mcp",
                headers=request_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                },
            )

            assert tools_response.status_code == 200
            tools = _sse_json(tools_response)["result"]["tools"]
            tool_names = {
                tool["name"]
                for tool in tools
            }
            assert {
                "search",
                "get_operator_basic_data",
                "get_operator_skill",
                "get_glossary",
                "get_operator_material",
                "get_operator_modules",
                "get_token_detail",
                "get_operator_skins",
                "get_material",
                "get_stage_data",
                "get_enemy_data",
                "recruit_with_tag",
                "get_integrated_strategy_collectible_detail",
            } <= tool_names
            assert "recruit" not in tool_names

            recruit_with_tag_tool = next(
                tool for tool in tools if tool["name"] == "recruit_with_tag"
            )
            assert set(recruit_with_tag_tool["inputSchema"]["properties"]) == {
                "tags"
            }
            assert recruit_with_tag_tool["inputSchema"]["required"] == ["tags"]
            tags_schema = recruit_with_tag_tool["inputSchema"]["properties"][
                "tags"
            ]
            assert tags_schema["type"] == "array"
            assert tags_schema["minItems"] == 1
            assert tags_schema["maxItems"] == 5
            assert "高级资深干员" in tags_schema["items"]["enum"]
            assert "女性干员" in tags_schema["items"]["enum"]
            assert "全部 5 个词条" in recruit_with_tag_tool["description"]
            assert "禁止自行组合" in recruit_with_tag_tool["description"]
            assert "直接向用户展示图片" in recruit_with_tag_tool["description"]
            assert (
                "不要自行计算、筛选或复述结果"
                in recruit_with_tag_tool["description"]
            )

            collectible_tool = next(
                tool
                for tool in tools
                if tool["name"] == "get_integrated_strategy_collectible_detail"
            )
            assert set(collectible_tool["inputSchema"]["properties"]) == {
                "collectible_id"
            }
            assert collectible_tool["inputSchema"]["required"] == [
                "collectible_id"
            ]
            assert "唯一" in collectible_tool["description"]

            skill_tool = next(tool for tool in tools if tool["name"] == "get_operator_skill")
            assert set(skill_tool["inputSchema"]["properties"]) == {"operator_id"}
            assert skill_tool["inputSchema"]["required"] == ["operator_id"]
            assert "完整技能列表" in skill_tool["description"]
            assert "全部等级数据" in skill_tool["description"]
