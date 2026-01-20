# src/entrypoints/uvicorn_host.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn

import asyncio
import logging

from fastapi.middleware.cors import CORSMiddleware
from src.app.bootstrap_disk import build_context_from_disk
from src.adapters.mcp.app import register_asgi
from src.app.card_fileservier import register_cardserver_asgi
from src.app.context import AppContext
from src.app.config import load_from_disk

log = logging.getLogger("asset")


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

    uvicorn.run(app, host="0.0.0.0", port=9000)
