from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from mcp.types import LATEST_PROTOCOL_VERSION

from src.adapters.mcp.app import register_asgi
from src.app.config import Config


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
            tool_names = {
                tool["name"]
                for tool in _sse_json(tools_response)["result"]["tools"]
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
            } <= tool_names
