"""
端到端测试：连接固定远端 MCP SSE 服务器，验证所有工具。

使用方式:
    # 使用默认远端服务器
    pytest tests/ -v

    # 针对本地开发服务器
    MCP_SERVER_URL=http://localhost:9000/mcp/sse pytest tests/ -v

    # 针对其他远端部署服务器
    MCP_SERVER_URL=https://amiya.example.com/mcp/sse pytest tests/ -v

    # 跳过需要服务端资源的测试（仅验证 MCP 握手和工具列表）
    pytest tests/ -v -k "not data"

环境变量:
    MCP_SERVER_URL     MCP SSE 端点地址（默认 https://amiyabot-mcp.hsyhhssyy.net/mcp/sse）
    MCP_REQUEST_TIMEOUT 请求超时秒数（默认 30）
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

# 确保项目 src 在 sys.path 中（本地开发时需要）
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.fail(f"缺少必需的环境变量: {name}")
    return value


# 端到端测试默认连接的固定远端服务器
_DEFAULT_MCP_SERVER_URL = "https://amiyabot-mcp.hsyhhssyy.net/mcp/sse"


@pytest.fixture(scope="session")
def mcp_server_url() -> str:
    """MCP SSE 服务端点地址。

    优先从环境变量 MCP_SERVER_URL 读取，未设置时使用固定远端地址。
    """
    return os.getenv("MCP_SERVER_URL", "").strip() or _DEFAULT_MCP_SERVER_URL


@pytest.fixture(scope="session")
def request_timeout() -> float:
    """HTTP 请求超时（秒）。"""
    return float(os.getenv("MCP_REQUEST_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# MCP 客户端会话（session 级别，复用连接）
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def mcp_session(mcp_server_url: str, request_timeout: float):
    """
    建立 MCP SSE 客户端会话，初始化并返回已就绪的 ClientSession。
    整个测试 session 共用同一连接。
    """
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client

    async with sse_client(url=mcp_server_url, timeout=request_timeout) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await session.initialize()
            print(f"\n[MCP] 已连接: server={init_result.serverInfo}")
            yield session


# ---------------------------------------------------------------------------
# 基础连通性测试
# ---------------------------------------------------------------------------

class TestConnectivity:
    """验证 MCP 连接和工具列表。"""

    async def test_initialize_success(self, mcp_session: Any) -> None:
        """初始化应成功并返回服务端信息。"""
        caps = mcp_session.get_server_capabilities()
        assert caps is not None, "服务器能力不应为空"

    async def test_list_tools(self, mcp_session: Any) -> None:
        """工具列表应包含全部 4 个已注册工具。"""
        result = await mcp_session.list_tools()
        tool_names = {t.name for t in result.tools}

        expected = {"search_operator", "get_operator_basic", "get_operator_skill", "get_glossary"}
        missing = expected - tool_names
        assert not missing, f"缺少工具: {missing}"

    async def test_send_ping(self, mcp_session: Any) -> None:
        """ping 应正常返回。"""
        # ping 不抛异常即为成功
        await mcp_session.send_ping()


# ---------------------------------------------------------------------------
# 工具功能测试
# ---------------------------------------------------------------------------

class TestSearchOperator:
    """测试 search_operator 工具。"""

    @pytest.mark.parametrize("query", ["阿米娅", "凯尔希", "银灰"])
    async def test_search_known_operator(self, mcp_session: Any, query: str) -> None:
        """搜索已知干员应返回结果。"""
        result = await mcp_session.call_tool("search_operator", {"query": query})
        assert result.isError is False, f"工具返回错误(query={query}): {result.content}"

        # 解析文本内容
        text = _extract_text(result)
        data = json.loads(text)
        assert "data" in data, f"响应缺少 data 字段(query={query}): {data}"
        operators = data.get("data", {}).get("operators", [])
        assert len(operators) > 0, f"搜索 '{query}' 应至少返回一个干员"

    async def test_search_empty_query(self, mcp_session: Any) -> None:
        """空查询应正常返回（不崩溃）。"""
        result = await mcp_session.call_tool("search_operator", {"query": ""})
        # 空查询不应报错
        assert result.isError is False


class TestGetOperatorBasic:
    """测试 get_operator_basic 工具。"""

    @pytest_asyncio.fixture(scope="class")
    async def amiya_id(self, mcp_session: Any) -> str:
        """先搜索阿米娅拿到 operator_id。"""
        result = await mcp_session.call_tool("search_operator", {"query": "阿米娅"})
        text = _extract_text(result)
        data = json.loads(text)
        operators = data.get("data", {}).get("operators", [])
        assert operators, "搜索阿米娅应返回结果"
        return operators[0]["id"]

    async def test_get_basic_by_id(self, mcp_session: Any, amiya_id: str) -> None:
        """通过 ID 获取干员基础信息。"""
        result = await mcp_session.call_tool("get_operator_basic", {"operator_id": amiya_id})
        assert result.isError is False, f"工具返回错误: {result.content}"

        text = _extract_text(result)
        data = json.loads(text)
        assert "data" in data, f"响应缺少 data 字段: {data}"
        basic = data["data"]
        assert "name" in basic, "干员信息应包含 name 字段"

    async def test_get_basic_invalid_id(self, mcp_session: Any) -> None:
        """无效 ID 应返回错误信息而非崩溃。"""
        result = await mcp_session.call_tool("get_operator_basic", {"operator_id": "nonexistent_999"})
        # 无效 ID 可能返回 isError=True 或 data 中包含错误信息
        # 重点是不应抛出未处理异常
        assert result is not None


class TestGetOperatorSkill:
    """测试 get_operator_skill 工具。"""

    @pytest_asyncio.fixture(scope="class")
    async def amiya_id(self, mcp_session: Any) -> str:
        """先搜索阿米娅拿到 operator_id。"""
        result = await mcp_session.call_tool("search_operator", {"query": "阿米娅"})
        text = _extract_text(result)
        data = json.loads(text)
        operators = data.get("data", {}).get("operators", [])
        assert operators
        return operators[0]["id"]

    async def test_get_skill_default(self, mcp_session: Any, amiya_id: str) -> None:
        """默认参数获取技能（技能1，等级10）。"""
        result = await mcp_session.call_tool(
            "get_operator_skill",
            {"operator_id": amiya_id},
        )
        assert result.isError is False, f"工具返回错误: {result.content}"

    async def test_get_skill_with_index_level(self, mcp_session: Any, amiya_id: str) -> None:
        """指定技能序号和等级。"""
        result = await mcp_session.call_tool(
            "get_operator_skill",
            {"operator_id": amiya_id, "index": 1, "level": 7},
        )
        assert result.isError is False, f"工具返回错误: {result.content}"


class TestGetGlossary:
    """测试 get_glossary 工具。"""

    async def test_query_single_term(self, mcp_session: Any) -> None:
        """查询单个术语。"""
        result = await mcp_session.call_tool("get_glossary", {"glossary_name": "攻击力"})
        assert result.isError is False, f"工具返回错误: {result.content}"

        text = _extract_text(result)
        data = json.loads(text)
        assert isinstance(data, dict), "术语查询应返回字典"
        # 应至少包含查询的术语
        assert len(data) > 0, "应至少返回一个术语"

    async def test_query_multiple_terms_list(self, mcp_session: Any) -> None:
        """以列表形式查询多个术语。"""
        result = await mcp_session.call_tool(
            "get_glossary",
            {"glossary_name": ["攻击力", "防御力"]},
        )
        assert result.isError is False

        text = _extract_text(result)
        data = json.loads(text)
        assert isinstance(data, dict)
        # 至少应返回其中一个术语
        assert len(data) > 0

    async def test_query_comma_separated(self, mcp_session: Any) -> None:
        """以逗号分隔字符串查询术语。"""
        result = await mcp_session.call_tool(
            "get_glossary",
            {"glossary_name": "攻击力,防御力"},
        )
        assert result.isError is False

        text = _extract_text(result)
        data = json.loads(text)
        assert isinstance(data, dict)
        assert len(data) > 0

    async def test_query_nonexistent_term(self, mcp_session: Any) -> None:
        """查询不存在的术语应正常返回（可能为空字典）。"""
        result = await mcp_session.call_tool(
            "get_glossary",
            {"glossary_name": "不存在的术语_xyz"},
        )
        assert result.isError is False
        # 不存在术语时不报错，返回结果即可


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _extract_text(result: Any) -> str:
    """从 CallToolResult 中提取第一个文本内容。"""
    for item in result.content:
        if hasattr(item, "text"):
            return item.text
    return "{}"
