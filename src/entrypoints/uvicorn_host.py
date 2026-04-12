# src/entrypoints/uvicorn_host.py
from dataclasses import replace
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from contextlib import asynccontextmanager
import uvicorn

import asyncio
import logging

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.app.bootstrap_disk import build_context_from_disk
from src.adapters.mcp.app import register_asgi
from src.adapters.cmd.app import execute_registered_command
from src.app.card_fileservier import register_cardserver_asgi
from src.app.context import AppContext
from src.app.config import load_from_disk

log = logging.getLogger("asset")
LOCAL_REQUEST_HOSTS = {"127.0.0.1", "::1", "localhost"}


class CommandExecuteRequest(BaseModel):
    command: str
    args: str = ""


async def _periodic_update_loop(app: FastAPI, interval_seconds: int = 15 * 60):
    while True:
        await asyncio.sleep(interval_seconds)

        ctx = getattr(app.state, "ctx", None)
        if not isinstance(ctx, AppContext):
            continue
        if not ctx.data_repository:
            continue

        try:
            await ctx.data_repository.update_and_refresh()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("data_repository.update failed")


def uvicorn_main():

    cfg = load_from_disk()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx = await build_context_from_disk(cfg)
        app.state.ctx = ctx

        task = asyncio.create_task(_periodic_update_loop(app, interval_seconds=15 * 60))

        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # 用 "*" 时必须 False
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Length", "Content-Type"],
        max_age=86400,
    )

    register_cardserver_asgi(app, cfg=cfg)
    register_asgi(app)

    @app.get("/rest/status")
    async def status():
        return {"status": "ok"}

    @app.post("/rest/commands/execute")
    async def execute_command(request: Request, payload: CommandExecuteRequest):
        ctx = getattr(app.state, "ctx", None)
        if payload.command not in {"help", "exit", "config-path"} and not isinstance(ctx, AppContext):
            raise HTTPException(status_code=503, detail="应用上下文未就绪")

        request_ctx = ctx
        if isinstance(ctx, AppContext):
            request_ctx = replace(
                ctx,
                prefer_local_artifact_path=(request.client is not None and request.client.host in LOCAL_REQUEST_HOSTS),
            )

        result = await execute_registered_command(request_ctx, payload.command, payload.args)
        return result.to_response()

    uvicorn.run(app, host="0.0.0.0", port=9000)
