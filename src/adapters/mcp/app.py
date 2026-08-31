import logging
from time import perf_counter
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi import Request
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.datastructures import Headers
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp
from starlette.types import Message
from starlette.types import Receive
from starlette.types import Scope
from starlette.types import Send

from src.adapters.mcp.mcp_tools.arknights_glossary import register_glossary_tool
# AI-REMOVED 2026-08-13:
# Reason: get_operator_card 工具已按用户要求移除，图片输出并入 get_operator_basic_data（card_image_url）。
# Trigger: MCP 工具说明重构需求（合并卡片与详情工具、字段改名）。
# Evidence: 对应注册调用与工具清单同步移除；底层查询 query_operator_basic_by_id 保持共用。
# Replacement: get_operator_basic_data 返回 card_image_url。
# Risk: Low（服务端内部）——旧客户端若仍调用 get_operator_card 将收到协议层"工具不存在"错误，需同步更新客户端。
# Human Review: Required
#
# Original code:
# from src.adapters.mcp.mcp_tools.operator_basic import register_operator_basic_data_tool, register_operator_card_tool
from src.adapters.mcp.mcp_tools.operator_basic import register_operator_basic_data_tool
from src.adapters.mcp.mcp_tools.operator_material import register_operator_material_tool
from src.adapters.mcp.mcp_tools.operator_modules import register_operator_modules_tool
from src.adapters.mcp.mcp_tools.search import register_search_tool
from src.adapters.mcp.mcp_tools.token_detail import register_token_detail_tool
from src.adapters.mcp.mcp_tools.operator_skins import register_operator_skins_tool
from src.adapters.mcp.mcp_tools.operator_skill import register_operator_skill_tool
from src.adapters.mcp.mcp_tools.material import register_material_tool
from src.adapters.mcp.mcp_tools.stage import register_stage_tool
from src.adapters.mcp.mcp_tools.enemy import register_enemy_tool
from src.app.config import Config

logger = logging.getLogger(__name__)


class MCPRequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        if path != "/mcp" and not path.startswith("/mcp/"):
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        headers = Headers(scope=scope)
        client = scope.get("client")
        client_host = client[0] if client else "unknown"
        query = (scope.get("query_string") or b"").decode("latin-1")
        method = str(scope.get("method") or "")
        host = headers.get("host", "")
        origin = headers.get("origin", "")
        user_agent = headers.get("user-agent", "")

        logger.info(
            "MCP 请求开始: method=%s path=%s query=%s client=%s host=%s origin=%s user_agent=%s",
            method,
            path,
            query,
            client_host,
            host,
            origin,
            user_agent,
        )

        status_code: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 0) or 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            logger.exception(
                "MCP 请求异常: method=%s path=%s elapsed_ms=%s client=%s host=%s",
                method,
                path,
                elapsed_ms,
                client_host,
                host,
            )
            raise

        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.info(
            "MCP 请求结束: method=%s path=%s status=%s elapsed_ms=%s client=%s host=%s",
            method,
            path,
            status_code if status_code is not None else "unknown",
            elapsed_ms,
            client_host,
            host,
        )

server_instructions = """
本服务器是一个游戏<明日方舟>的知识库查询助手，专注于为用户提供准确的干员信息数据和游戏资料。
你可以使用注册的工具来回答明日方舟游戏内的问题。
任何查询都请先调用 search 获取候选实体的 id（干员、召唤物、皮肤、材料、关卡、敌人或集成战略藏品），再用该 id 调用对应的详情工具（干员基础资料：get_operator_basic_data；干员完整技能列表及全部等级：get_operator_skill；干员培养材料：get_operator_material；干员模组：get_operator_modules；召唤物：get_token_detail；皮肤：get_operator_skins；材料：get_material；关卡：get_stage_data；敌人：get_enemy_data）。集成战略藏品的描述、效果、稀有度、解锁条件和所属主题由 search 直接返回；图标缓存成功时通过 icon_url 返回，目前没有独立详情工具。
"""


def _format_host(hostname: str) -> str:
    if ":" in hostname and not hostname.startswith("["):
        return f"[{hostname}]"
    return hostname


def _build_transport_security(base_url: str | None, enabled: bool) -> TransportSecuritySettings:
    if not enabled:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    allowed_hosts = {
        "127.0.0.1",
        "127.0.0.1:80",
        "127.0.0.1:443",
        "127.0.0.1:*",
        "localhost",
        "localhost:80",
        "localhost:443",
        "localhost:*",
        "[::1]",
        "[::1]:80",
        "[::1]:443",
        "[::1]:*",
    }
    allowed_origins = {
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
        "https://127.0.0.1:*",
        "https://localhost:*",
        "https://[::1]:*",
    }

    if base_url:
        parsed = urlsplit(base_url)
        if parsed.scheme and parsed.hostname:
            formatted_host = _format_host(parsed.hostname.lower())
            allowed_hosts.add(formatted_host)
            if parsed.port is not None:
                allowed_hosts.add(f"{formatted_host}:{parsed.port}")
            elif parsed.scheme == "http":
                allowed_hosts.add(f"{formatted_host}:80")
            elif parsed.scheme == "https":
                allowed_hosts.add(f"{formatted_host}:443")

            allowed_origins.add(f"{parsed.scheme.lower()}://{parsed.netloc.lower()}")

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=sorted(allowed_hosts),
        allowed_origins=sorted(allowed_origins),
    )


def _register_mcp_request_logging(app: FastAPI) -> None:
    if getattr(app.state, "_mcp_request_logging_registered", False):
        return

    app.add_middleware(MCPRequestLoggingMiddleware)

    app.state._mcp_request_logging_registered = True


def register_asgi(app: FastAPI, cfg: Config) -> FastMCP:
    _register_mcp_request_logging(app)

    transport_security = _build_transport_security(
        cfg.BaseUrl,
        cfg.McpDnsRebindingProtectionEnabled,
    )

    logger.info(
        "开始注册 MCP ASGI: base_url=%s dns_rebinding_protection=%s",
        cfg.BaseUrl,
        cfg.McpDnsRebindingProtectionEnabled,
    )
    logger.info(
        "MCP 传输安全配置: allowed_hosts=%s allowed_origins=%s",
        getattr(transport_security, "allowed_hosts", None),
        getattr(transport_security, "allowed_origins", None),
    )

    # Streamable HTTP 对外使用单一 /mcp 端点。这个挂载必须放在
    # FastAPI 其他路由之后，因为 Mount("/") 会匹配所有剩余路径。
    # "amiya-mcp": {
    #   "transport":"streamable-http",
    #   "url": "http://localhost:9000/mcp"
    # }
    mcp = FastMCP(
        "明日方舟知识库",
        instructions=server_instructions,
        mount_path="/mcp/sse",
        sse_path="/",
        # 工具调用不依赖跨请求的客户端状态。使用无状态 Streamable HTTP
        # 可以避免服务重启后客户端继续携带已失效 Mcp-Session-Id 而持续 404。
        stateless_http=True,
        transport_security=transport_security,
    )

    register_glossary_tool(mcp,app)
    register_search_tool(mcp,app)
    register_operator_basic_data_tool(mcp,app)
    # AI-REMOVED 2026-08-13:
    # Reason: get_operator_card 工具已移除，图片输出并入 get_operator_basic_data（card_image_url）。
    # Trigger: 用户要求合并卡片与详情工具。
    # Evidence: import 与工具清单同步移除。
    # Replacement: get_operator_basic_data 返回 card_image_url。
    # Risk: Low。Human Review: Required。
    #
    # Original code:
    # register_operator_card_tool(mcp,app)
    register_operator_skill_tool(mcp,app)
    register_operator_material_tool(mcp,app)
    register_operator_modules_tool(mcp,app)
    register_token_detail_tool(mcp,app)
    register_operator_skins_tool(mcp,app)
    register_material_tool(mcp,app)
    register_stage_tool(mcp,app)
    register_enemy_tool(mcp,app)
    logger.info(
        "MCP 工具注册完成: tools=%s",
        ["get_glossary", "search", "get_operator_basic_data", "get_operator_skill", "get_operator_material", "get_operator_modules", "get_token_detail", "get_operator_skins", "get_material", "get_stage_data", "get_enemy_data"],
    )

    streamable_http_app = mcp.streamable_http_app()
    app.state.mcp_session_manager = mcp.session_manager
    # 保留旧 SSE URL 作为迁移期兼容入口。子应用的根路由会使
    # /mcp/sse 重定向到 /mcp/sse/，官方客户端会跟随该重定向。
    @app.get("/mcp/sse", include_in_schema=False)
    async def redirect_legacy_sse(request: Request) -> RedirectResponse:
        root_path = str(request.scope.get("root_path") or "").rstrip("/")
        return RedirectResponse(f"{root_path}{request.url.path}/", status_code=307)

    app.mount("/mcp/sse", mcp.sse_app(), name="mcp-legacy-sse")
    app.mount("/", streamable_http_app, name="mcp-streamable-http")
    logger.info(
        "MCP ASGI 挂载完成: streamable_http_endpoint=/mcp legacy_sse_endpoint=/mcp/sse"
    )
    return mcp
