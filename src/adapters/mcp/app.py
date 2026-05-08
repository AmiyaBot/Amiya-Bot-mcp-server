#src/adapters/mcp/app.py
from urllib.parse import urlsplit

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from src.adapters.mcp.mcp_tools.arknights_glossary import register_glossary_tool
from src.adapters.mcp.mcp_tools.operator_basic import register_operator_basic_tool
from src.adapters.mcp.mcp_tools.operator_skill import register_operator_skill_tool
from src.app.config import Config

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


def register_asgi(app: FastAPI, cfg: Config):

    # 挂载 FastMCP 的 SSE 应用到 FastAPI 的 /mcp 路径下
    # "amiya-mcp": {
    #   "transport":"sse",
    #   "url": "http://localhost:9000/mcp/sse"
    # }
    mcp = FastMCP(
        "明日方舟知识库",
        instructions=server_instructions,
        transport_security=_build_transport_security(
            cfg.BaseUrl,
            cfg.McpDnsRebindingProtectionEnabled,
        ),
    )

    register_glossary_tool(mcp,app)
    register_operator_basic_tool(mcp,app)
    register_operator_skill_tool(mcp,app)

    app.mount("/mcp", mcp.sse_app())
