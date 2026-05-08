import logging
from time import perf_counter
from urllib.parse import urlsplit

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.datastructures import Headers
from starlette.types import ASGIApp
from starlette.types import Message
from starlette.types import Receive
from starlette.types import Scope
from starlette.types import Send

from src.adapters.mcp.mcp_tools.arknights_glossary import register_glossary_tool
from src.adapters.mcp.mcp_tools.operator_basic import register_operator_basic_tool
from src.adapters.mcp.mcp_tools.operator_skill import register_operator_skill_tool
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


def register_asgi(app: FastAPI, cfg: Config):
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

    # 挂载 FastMCP 的 SSE 应用到 FastAPI 的 /mcp 路径下
    # "amiya-mcp": {
    #   "transport":"sse",
    #   "url": "http://localhost:9000/mcp/sse"
    # }
    mcp = FastMCP(
        "明日方舟知识库",
        instructions=server_instructions,
        transport_security=transport_security,
    )

    register_glossary_tool(mcp,app)
    register_operator_basic_tool(mcp,app)
    register_operator_skill_tool(mcp,app)
    logger.info(
        "MCP 工具注册完成: tools=%s",
        ["get_glossary", "get_operator_basic", "get_operator_skill"],
    )

    app.mount("/mcp", mcp.sse_app())
    logger.info("MCP ASGI 挂载完成: mount_path=/mcp sse_path=/mcp/sse")
