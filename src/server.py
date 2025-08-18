from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

# 创建 FastAPI 应用
app = FastAPI()

# 挂载 FastMCP 的 SSE 应用到 FastAPI 的 /mcp 路径下
# "amiya-mcp": {
#   "transportType":"sse",
#   "url": "http://localhost:9000/mcp/sse"
# }
mcp = FastMCP("明日方舟知识库")
mcp.settings.mount_path = "/mcp"
app.mount("/mcp", mcp.sse_app())

# 定义一个简单的状态检查路由
@app.get("/rest/status")
async def status():
    return {"status": "ok"}
