import logging
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from functools import wraps


# 创建 FastAPI 应用
app = FastAPI()

# 挂载 FastMCP 的 SSE 应用到 FastAPI 的 /mcp 路径下
# "amiya-mcp": {
#   "transportType":"sse",
#   "url": "http://localhost:9000/mcp/sse"
# }
mcp = FastMCP("明日方舟知识库")
app.mount("/mcp", mcp.sse_app())

mcp_logger = logging.getLogger("mcp")
mcp_logger.setLevel(logging.INFO)  # 默认日志等级

# 定义一个简单的状态检查路由
@app.get("/rest/status")
async def status():
    return {"status": "ok"}
