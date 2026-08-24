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

# 确保项目 src 在 sys.path 中（本地开发时需要）
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# 使用 anyio 自带的 pytest 插件运行本套件（而非 pytest-asyncio）：
# sse_client 内部使用 anyio task group，其 cancel scope 要求在同一 task 中进入与退出；
# anyio 插件把 fixture 的 setup/teardown 与测试都调度到同一个常驻 runner task 中，
# 而 pytest-asyncio 会在不同 task 中执行 fixture teardown，导致
# "Attempted to exit cancel scope in a different task" 崩溃。
pytestmark = pytest.mark.anyio


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

@pytest.fixture(scope="function")
async def mcp_session(mcp_server_url: str, request_timeout: float):
    """
    建立 MCP SSE 客户端会话，初始化并返回已就绪的 ClientSession。
    每个测试独立建立连接。
    """
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client

    # sse_client 的 anyio task group 依赖同一 task 内完成 setup/teardown，
    # 因此本套件必须由 anyio 的 pytest 插件运行（见模块级 pytestmark 说明）。
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
        """工具列表应包含全部 8 个已注册工具。"""
        result = await mcp_session.list_tools()
        tool_names = {t.name for t in result.tools}

        expected = {"search", "get_operator_basic_data", "get_operator_skill", "get_glossary", "get_operator_material", "get_operator_modules", "get_token_detail", "get_operator_skins"}
        missing = expected - tool_names
        assert not missing, f"缺少工具: {missing}"

    async def test_send_ping(self, mcp_session: Any) -> None:
        """ping 应正常返回。"""
        # ping 不抛异常即为成功
        await mcp_session.send_ping()


# ---------------------------------------------------------------------------
# 工具功能测试
# ---------------------------------------------------------------------------

class TestSearch:
    """测试 search 工具（资源统一搜索）。"""

    @pytest.mark.parametrize("query", ["阿米娅", "凯尔希", "银灰"])
    async def test_search_known_operator(self, mcp_session: Any, query: str) -> None:
        """搜索已知干员应返回结果。"""
        result = await mcp_session.call_tool("search", {"query": query})
        assert result.isError is False, f"工具返回错误(query={query}): {result.content}"

        # 解析文本内容
        text = _extract_text(result)
        data = json.loads(text)
        assert "data" in data, f"响应缺少 data 字段(query={query}): {data}"
        items = data.get("data", {}).get("items", [])
        assert len(items) > 0, f"搜索 '{query}' 应至少返回一个结果"
        assert any(item.get("type") == "干员" for item in items), f"搜索 '{query}' 应返回干员条目"

    async def test_search_known_token(self, mcp_session: Any) -> None:
        """搜索召唤物名称应返回召唤物条目（携带所属干员信息）。"""
        result = await mcp_session.call_tool("search", {"query": "Mon3tr"})
        assert result.isError is False, f"工具返回错误: {result.content}"

        text = _extract_text(result)
        data = json.loads(text)
        items = data.get("data", {}).get("items", [])
        assert len(items) > 0, "搜索 'Mon3tr' 应至少返回一个结果"

        token_items = [item for item in items if item.get("type") == "召唤物"]
        assert token_items, f"搜索 'Mon3tr' 应返回召唤物条目: {items}"
        for item in token_items:
            assert item.get("operator_id"), f"召唤物条目应携带 operator_id: {item}"

    async def test_search_known_skin(self, mcp_session: Any) -> None:
        """搜索皮肤名应返回皮肤条目（携带归属干员信息）。"""
        result = await mcp_session.call_tool("search", {"query": "报童"})
        assert result.isError is False, f"工具返回错误: {result.content}"

        text = _extract_text(result)
        data = json.loads(text)
        items = data.get("data", {}).get("items", [])
        assert len(items) > 0, "搜索 '报童' 应至少返回一个结果"

        skin_items = [item for item in items if item.get("type") == "皮肤"]
        assert skin_items, f"搜索 '报童' 应返回皮肤条目: {items}"
        for item in skin_items:
            assert item.get("operator_id"), f"皮肤条目应携带 operator_id: {item}"
            assert item.get("operator_name"), f"皮肤条目应携带 operator_name: {item}"

    async def test_search_empty_query(self, mcp_session: Any) -> None:
        """空查询应正常返回（不崩溃）。"""
        result = await mcp_session.call_tool("search", {"query": ""})
        # 空查询不应报错
        assert result.isError is False


class TestGetOperatorSkins:
    """测试 get_operator_skins 工具 — 皮肤选择卡 + 结构化列表 + 单项图片 URL。"""

    async def test_get_operator_skins(self, mcp_session: Any) -> None:
        """按干员 ID 查询应返回皮肤列表，且条目携带皮肤字段。"""
        result = await mcp_session.call_tool(
            "get_operator_skins",
            {"operator_id": "char_210_stward"},
        )
        assert result.isError is False, f"工具返回错误: {result.content}"

        text = _extract_text(result)
        data = json.loads(text)
        payload = data.get("data", {})
        operator = payload.get("operator", {})
        assert operator.get("id") == "char_210_stward", f"应返回 operator: {operator}"

        skins = payload.get("skins", [])
        assert len(skins) > 0, f"应至少返回一个皮肤条目: {payload}"
        for item in skins:
            assert item.get("id"), f"皮肤条目应携带 id: {item}"
            assert item.get("名称"), f"皮肤条目应携带名称: {item}"
            assert "card_url" in item, f"皮肤条目应携带 card_url 字段: {item}"

        selection_card_url = data.get("card_image_url")
        if selection_card_url:
            assert payload.get("selection_card_url") == selection_card_url
            assert [item.get("序号") for item in skins] == list(range(1, len(skins) + 1))

    async def test_get_operator_skins_invalid_id(self, mcp_session: Any) -> None:
        """不存在的干员 ID 应返回提示。"""
        result = await mcp_session.call_tool(
            "get_operator_skins",
            {"operator_id": "char_9999_not_exist"},
        )
        assert result.isError is False
        text = _extract_text(result)
        data = json.loads(text)
        assert "未找到干员ID" in (data.get("message") or ""), f"应返回未找到提示: {data}"


class TestGetTokenDetail:
    """测试 get_token_detail 工具 — 召唤物详情（结构化数据 + 卡片图片）。"""

    @pytest.fixture(scope="function")
    async def token_id(self, mcp_session: Any) -> str:
        """通过 search 找到召唤物条目 id。"""
        result = await mcp_session.call_tool("search", {"query": "Mon3tr"})
        text = _extract_text(result)
        data = json.loads(text)
        items = data.get("data", {}).get("items", [])
        token_items = [item for item in items if item.get("type") == "召唤物"]
        assert token_items, f"搜索 'Mon3tr' 应返回召唤物条目: {items}"
        return token_items[0]["id"]

    async def test_get_token_detail_returns_data(self, mcp_session: Any, token_id: str) -> None:
        """获取召唤物详情应返回结构化数据与所属干员信息。"""
        result = await mcp_session.call_tool("get_token_detail", {"token_id": token_id})
        assert result.isError is False, f"工具返回错误: {result.content}"

        text = _extract_text(result)
        data = json.loads(text)

        if "message" in data and "data" not in data:
            pytest.fail(f"服务端返回错误: {data['message']}")

        detail = data.get("data", {})
        assert isinstance(detail, dict) and detail, f"召唤物数据为空: {data}"
        assert detail.get("名称") == "Mon3tr", f"召唤物名称不符: {detail.get('名称')}"
        assert detail.get("所属干员", {}).get("名称") == "凯尔希", f"所属干员信息不符: {detail.get('所属干员')}"

        # 契约：图片字段为 card_image_url（2026-08-13 由 image_url 更名）。
        # 远端部署可能仍运行旧代码（返回 image_url，甚至不返回图片字段），此处兼容；
        # 指向本仓库新代码的部署时，可改为严格断言 "card_image_url" in data。
        card_url = data.get("card_image_url") or data.get("image_url")
        if not card_url:
            pytest.skip("服务端未返回卡片图片 URL（可能为旧版本部署）")
        assert isinstance(card_url, str) and card_url, f"卡片图片 URL 无效: {data}"

    async def test_get_token_detail_invalid_id(self, mcp_session: Any) -> None:
        """无效召唤物 ID 应返回错误信息而非崩溃。"""
        result = await mcp_session.call_tool("get_token_detail", {"token_id": "token_nonexistent_999"})
        assert result is not None


class TestGetOperatorBasicData:
    """测试 get_operator_basic_data 工具 — 返回结构化数据与卡片图片 URL（card_image_url）。"""

    @pytest.fixture(scope="function")
    async def operator_ids(self, mcp_session: Any) -> dict[str, str]:
        ids: dict[str, str] = {}
        for name in ["阿米娅", "凯尔希", "银灰"]:
            result = await mcp_session.call_tool("search", {"query": name})
            text = _extract_text(result)
            data = json.loads(text)
            items = data.get("data", {}).get("items", [])
            assert items, f"搜索 {name} 应返回结果"
            ids[name] = items[0]["id"]
        return ids

    @pytest.mark.parametrize("operator_name", ["阿米娅", "凯尔希", "银灰"])
    async def test_get_basic_data_fields(
        self, mcp_session: Any, operator_ids: dict[str, str], operator_name: str
    ) -> None:
        """get_operator_basic_data 应返回结构化数据与 card_image_url 卡片图片。"""
        op_id = operator_ids[operator_name]
        result = await mcp_session.call_tool("get_operator_basic_data", {"operator_id": op_id})
        assert result.isError is False, f"工具返回错误(operator={operator_name}): {result.content}"

        text = _extract_text(result)
        data = json.loads(text)

        if "message" in data and "data" not in data:
            pytest.fail(f"服务端返回错误: {data['message']}")

        # 原 get_operator_card 工具已移除，图片字段改名为 card_image_url 并入本工具返回。
        # 远端部署可能仍返回旧字段名 image_url 或尚未返回图片字段，此处兼容；
        # 指向本仓库新代码的部署时，可改为严格断言 "card_image_url" in data。
        card_url = data.get("card_image_url") or data.get("image_url")
        if not card_url:
            pytest.skip(f"服务端未返回卡片图片 URL（可能为旧版本部署）(operator={operator_name})")
        assert isinstance(card_url, str) and len(card_url) > 0, f"卡片图片 URL 无效(operator={operator_name})"

        card = data.get("data", {})
        assert isinstance(card, dict) and card, f"数据为空(operator={operator_name})"

        # 验证中文键层级
        name_section = card.get("名称", {})
        assert name_section.get("中文名") == operator_name
        class_section = card.get("分类", {})
        assert "稀有度" in class_section
        assert "职业" in class_section
        assert "基础档案" in card
        assert isinstance(card.get("属性", {}), dict) and len(card["属性"]) > 0

    async def test_get_basic_data_invalid_id(self, mcp_session: Any) -> None:
        """无效 ID 应返回错误信息而非崩溃。"""
        result = await mcp_session.call_tool("get_operator_basic_data", {"operator_id": "nonexistent_999"})
        assert result is not None


class TestGetOperatorModules:
    """测试 get_operator_modules 工具 — 模组卡片与完整结构化数据。"""

    async def test_get_operator_modules(self, mcp_session: Any) -> None:
        result = await mcp_session.call_tool(
            "get_operator_modules",
            {"operator_id": "char_172_svrash"},
        )
        assert result.isError is False, f"工具返回错误: {result.content}"

        data = json.loads(_extract_text(result))
        if "message" in data and "data" not in data:
            pytest.fail(f"服务端返回错误: {data['message']}")

        payload = data.get("data", {})
        assert payload.get("干员", {}).get("中文名") == "银灰"
        modules = payload.get("模组", [])
        assert modules, f"应至少返回一个模组: {payload}"
        advanced = next(item for item in modules if item.get("等级数据"))
        assert len(advanced["等级数据"]) == 3
        assert advanced.get("解锁条件", {}).get("任务")

    async def test_get_operator_modules_invalid_id(self, mcp_session: Any) -> None:
        result = await mcp_session.call_tool(
            "get_operator_modules",
            {"operator_id": "char_9999_not_exist"},
        )
        assert result.isError is False
        data = json.loads(_extract_text(result))
        assert "未找到干员ID" in (data.get("message") or "")


# AI-REMOVED 2026-08-13:
# Reason: get_operator_card 工具已移除，其图片输出并入 get_operator_basic_data（card_image_url 字段）。
# Trigger: 用户要求重构 MCP 工具说明——合并卡片与详情工具、URL 字段改名。
# Evidence: 服务端 app.py 注册列表已移除该工具；对应端到端断言已迁移至 TestGetOperatorBasicData。
# Replacement: TestGetOperatorBasicData.test_get_basic_data_fields 新增 card_image_url 断言。
# Risk: Low。Human Review: Required。
#
# Original code:
# class TestGetOperatorCard:
#     """测试 get_operator_card 工具 — 仅返回图片 URL。"""
#
#     @pytest_asyncio.fixture(scope="function")
#     async def operator_ids(self, mcp_session: Any) -> dict[str, str]:
#         ids: dict[str, str] = {}
#         for name in ["阿米娅", "凯尔希", "银灰"]:
#             result = await mcp_session.call_tool("search", {"query": name})
#             text = _extract_text(result)
#             data = json.loads(text)
#             items = data.get("data", {}).get("items", [])
#             assert items, f"搜索 {name} 应返回结果"
#             ids[name] = items[0]["id"]
#         return ids
#
#     @pytest.mark.parametrize("operator_name", ["阿米娅", "凯尔希", "银灰"])
#     async def test_get_card_image_url(
#         self, mcp_session: Any, operator_ids: dict[str, str], operator_name: str
#     ) -> None:
#         """get_operator_card 应仅返回 image_url。"""
#         op_id = operator_ids[operator_name]
#         result = await mcp_session.call_tool("get_operator_card", {"operator_id": op_id})
#         assert result.isError is False, f"工具返回错误(operator={operator_name}): {result.content}"
#
#         text = _extract_text(result)
#         data = json.loads(text)
#
#         if "message" in data and "image_url" not in data:
#             pytest.skip(f"服务端未生成图片: {data['message']}")
#
#         # 应仅包含 image_url，不应包含 data
#         assert "image_url" in data, f"缺少 image_url(operator={operator_name})"
#         assert "data" not in data, f"get_operator_card 不应包含 data 字段(operator={operator_name})"
#         assert isinstance(data["image_url"], str) and len(data["image_url"]) > 0, f"image_url 无效(operator={operator_name})"
#
#     async def test_get_card_invalid_id(self, mcp_session: Any) -> None:
#         """无效 ID 应返回错误信息而非崩溃。"""
#         result = await mcp_session.call_tool("get_operator_card", {"operator_id": "nonexistent_999"})
#         assert result is not None


class TestGetOperatorSkill:
    """测试 get_operator_skill 工具 — 验证技能卡片内容。

    get_operator_skill 返回 {"data": "<markdown 字符串>"}，
    格式为多行文本包含干员名、技能名、等级、技力、技能效果等。
    """

    @pytest.fixture(scope="function")
    async def operator_ids(self, mcp_session: Any) -> dict[str, str]:
        """搜索阿米娅、凯尔希、银灰，返回 {name: id}。"""
        ids: dict[str, str] = {}
        for name in ["阿米娅", "凯尔希", "银灰"]:
            result = await mcp_session.call_tool("search", {"query": name})
            text = _extract_text(result)
            data = json.loads(text)
            items = data.get("data", {}).get("items", [])
            assert items, f"搜索 {name} 应返回结果"
            ids[name] = items[0]["id"]
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
