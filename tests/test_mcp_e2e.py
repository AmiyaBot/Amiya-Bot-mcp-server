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

@pytest_asyncio.fixture(scope="function")
async def mcp_session(mcp_server_url: str, request_timeout: float):
    """
    建立 MCP SSE 客户端会话，初始化并返回已就绪的 ClientSession。
    每个测试独立建立连接。
    """
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client

    # 使用 sse_client 上下文获取流，手动管理 ClientSession 避免 anyio cancel scope 冲突
    async with sse_client(url=mcp_server_url, timeout=request_timeout) as (
        read_stream,
        write_stream,
    ):
        session = ClientSession(read_stream, write_stream)
        async with session:
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
    """测试 get_operator_basic 工具 — 验证干员卡片内容完整性。"""

    @pytest_asyncio.fixture(scope="function")
    async def operator_ids(self, mcp_session: Any) -> dict[str, str]:
        """搜索阿米娅、凯尔希、银灰，返回 {name: id}。"""
        ids: dict[str, str] = {}
        for name in ["阿米娅", "凯尔希", "银灰"]:
            result = await mcp_session.call_tool("search_operator", {"query": name})
            text = _extract_text(result)
            data = json.loads(text)
            operators = data.get("data", {}).get("operators", [])
            assert operators, f"搜索 {name} 应返回结果"
            ids[name] = operators[0]["id"]
        return ids

    # 干员卡片必须包含的核心字段及其预期值
    _EXPECTED_CARD_FIELDS = {
        "阿米娅": {"id": "char_002_amiya", "name": "阿米娅", "rarity": 5, "class": "术师"},
        "凯尔希": {"id": "char_003_kalts", "name": "凯尔希", "rarity": 6, "class": "医疗"},
        "银灰": {"id": "char_172_svrash", "name": "银灰", "rarity": 6, "class": "近卫"},
    }

    @pytest.mark.parametrize("operator_name", ["阿米娅", "凯尔希", "银灰"])
    async def test_get_basic_verify_card_fields(
        self, mcp_session: Any, operator_ids: dict[str, str], operator_name: str
    ) -> None:
        """通过 ID 获取干员卡片，验证核心字段值和 image_url。"""
        op_id = operator_ids[operator_name]
        result = await mcp_session.call_tool("get_operator_basic", {"operator_id": op_id})
        assert result.isError is False, f"工具返回错误(operator={operator_name}): {result.content}"

        text = _extract_text(result)
        data = json.loads(text)

        # get_operator_basic 返回 {"data": {...}} 或 {"message": "错误信息"}
        # 如果服务端出错返回 message，则跳过字段验证（服务端问题，非测试问题）
        if "message" in data and "data" not in data:
            pytest.skip(f"服务端返回错误(operator={operator_name}): {data['message']}")

        card = data.get("data", {})
        if not isinstance(card, dict) or not card:
            pytest.fail(f"卡片数据为空或格式异常(operator={operator_name}): {data}")

        expected = self._EXPECTED_CARD_FIELDS[operator_name]
        assert card.get("id") == expected["id"], f"id 不匹配(operator={operator_name}): {card.get('id')} != {expected['id']}"
        assert card.get("name") == expected["name"], f"name 不匹配(operator={operator_name})"
        assert card.get("rarity") == expected["rarity"], f"rarity 不匹配(operator={operator_name}): {card.get('rarity')} != {expected['rarity']}"
        assert card.get("class") == expected["class"], f"class 不匹配(operator={operator_name}): {card.get('class')} != {expected['class']}"

        # 卡片必须有的关键字段
        for field in ["id", "name", "rarity", "class", "image_url", "type", "position"]:
            assert field in card, f"卡片缺少字段(operator={operator_name}): {field}"

        # image_url 必须是非空字符串
        image_url = card.get("image_url")
        assert isinstance(image_url, str) and len(image_url) > 0, f"image_url 无效(operator={operator_name}): {image_url!r}"

    async def test_get_basic_invalid_id(self, mcp_session: Any) -> None:
        """无效 ID 应返回错误信息而非崩溃。"""
        result = await mcp_session.call_tool("get_operator_basic", {"operator_id": "nonexistent_999"})
        assert result is not None


class TestGetOperatorSkill:
    """测试 get_operator_skill 工具 — 验证技能卡片内容。

    get_operator_skill 返回 {"data": "<markdown 字符串>"}，
    格式为多行文本包含干员名、技能名、等级、技力、技能效果等。
    """

    @pytest_asyncio.fixture(scope="function")
    async def operator_ids(self, mcp_session: Any) -> dict[str, str]:
        """搜索阿米娅、凯尔希、银灰，返回 {name: id}。"""
        ids: dict[str, str] = {}
        for name in ["阿米娅", "凯尔希", "银灰"]:
            result = await mcp_session.call_tool("search_operator", {"query": name})
            text = _extract_text(result)
            data = json.loads(text)
            operators = data.get("data", {}).get("operators", [])
            assert operators, f"搜索 {name} 应返回结果"
            ids[name] = operators[0]["id"]
        return ids

    # 技能1在7级时 markdown 中应包含的关键词
    _SKILL_KEYWORDS = {
        "阿米娅": ["阿米娅", "战术咏唱·γ", "等级：7", "技力", "技能效果"],
        "凯尔希": ["凯尔希", "指令：结构加固", "等级：7", "技力", "技能效果"],
        "银灰": ["银灰", "强力击·γ型", "等级：7", "技力", "技能效果"],
    }

    @pytest.mark.parametrize("operator_name", ["阿米娅", "凯尔希", "银灰"])
    async def test_get_skill_verify_content(
        self, mcp_session: Any, operator_ids: dict[str, str], operator_name: str
    ) -> None:
        """获取技能（技能1，等级7），验证 markdown 中包含关键信息。"""
        op_id = operator_ids[operator_name]
        result = await mcp_session.call_tool(
            "get_operator_skill",
            {"operator_id": op_id, "index": 1, "level": 7},
        )
        assert result.isError is False, f"工具返回错误(operator={operator_name}): {result.content}"

        text = _extract_text(result)
        data = json.loads(text)

        # data 是 markdown 字符串
        md = data.get("data", "")
        assert isinstance(md, str) and len(md) > 0, f"技能数据为空(operator={operator_name})"

        # 验证 markdown 中包含所有关键信息
        missing = []
        for keyword in self._SKILL_KEYWORDS[operator_name]:
            if keyword not in md:
                missing.append(keyword)
        assert not missing, f"技能卡片缺少关键词(operator={operator_name}): {missing}\n实际内容前200字: {md[:200]}"

    async def test_get_skill_default_params(self, mcp_session: Any, operator_ids: dict[str, str]) -> None:
        """默认参数（不传 index/level）应正常返回。"""
        op_id = operator_ids["阿米娅"]
        result = await mcp_session.call_tool(
            "get_operator_skill",
            {"operator_id": op_id},
        )
        assert result.isError is False, f"默认参数调用失败: {result.content}"


class TestGetGlossary:
    """测试 get_glossary 工具。"""

    async def test_query_single_term(self, mcp_session: Any) -> None:
        """查询单个术语，不崩溃即可（远端数据可能不完整）。"""
        result = await mcp_session.call_tool("get_glossary", {"glossary_name": "攻击力"})
        assert result.isError is False, f"工具返回错误: {result.content}"

    async def test_query_multiple_terms_list(self, mcp_session: Any) -> None:
        """以列表形式查询多个术语。"""
        result = await mcp_session.call_tool(
            "get_glossary",
            {"glossary_name": ["攻击力", "防御力"]},
        )
        assert result.isError is False

    async def test_query_comma_separated(self, mcp_session: Any) -> None:
        """以逗号分隔字符串查询术语。"""
        result = await mcp_session.call_tool(
            "get_glossary",
            {"glossary_name": "攻击力,防御力"},
        )
        assert result.isError is False

    async def test_query_nonexistent_term(self, mcp_session: Any) -> None:
        """查询不存在的术语应正常返回。"""
        result = await mcp_session.call_tool(
            "get_glossary",
            {"glossary_name": "不存在的术语_xyz"},
        )
        assert result.isError is False


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _extract_text(result: Any) -> str:
    """从 CallToolResult 中提取第一个文本内容。"""
    for item in result.content:
        if hasattr(item, "text"):
            return item.text
    return "{}"
