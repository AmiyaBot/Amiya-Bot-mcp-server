# src/entrypoints/uvicorn_host.py
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from contextlib import asynccontextmanager
from time import perf_counter
import uvicorn

import asyncio
import logging

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.app.bootstrap_disk import build_context_from_disk
from src.adapters.cmd.web_client import compute_service_code_revision
from src.adapters.cmd.web_client import resolve_service_git_sha
from src.adapters.mcp.app import register_asgi
from src.adapters.cmd.app import execute_registered_command
from src.app.card_fileservier import register_cardserver_asgi
from src.app.context import AppContext
from src.app.config import load_from_disk
from src.app.services.resource_update import read_resource_update_status
from src.app.services.operator_queries import search_operator
from src.app.transformers.html_to_png_transformer import probe_playwright_chromium

log = logging.getLogger("asset")
LOCAL_REQUEST_HOSTS = {"127.0.0.1", "::1", "localhost"}


class CommandExecuteRequest(BaseModel):
    command: str
    args: str = ""
    output_format: Literal["markdown", "json"] = "markdown"


def _normalize_operator_check_queries(raw_items: list[str] | None) -> list[str]:
    default_queries = ["阿米娅", "凯尔希", "陈"]
    if not raw_items:
        return default_queries

    queries: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        normalized = str(raw or "").replace("，", ",").replace("、", ",")
        for item in normalized.split(","):
            query = item.strip()
            if not query or query in seen:
                continue
            seen.add(query)
            queries.append(query)

    return queries or default_queries


def _build_path_summary(path: Path) -> dict[str, Any]:
    exists = path.exists()
    is_file = path.is_file() if exists else False
    is_dir = path.is_dir() if exists else False
    size = None
    if is_file:
        try:
            size = path.stat().st_size
        except OSError:
            size = None

    return {
        "path": str(path),
        "exists": exists,
        "is_file": is_file,
        "is_dir": is_dir,
        "size": size,
    }


def build_resource_check_payload(
    app: FastAPI,
    *,
    cfg,
    operator_names: list[str] | None = None,
) -> dict[str, Any]:
    ctx = getattr(app.state, "ctx", None)
    repository = getattr(ctx, "data_repository", None) if isinstance(ctx, AppContext) else None
    update_status = read_resource_update_status(cfg)
    queries = _normalize_operator_check_queries(operator_names)

    payload: dict[str, Any] = {
        "status": "ok",
        "code_revision": getattr(app.state, "code_revision", "unknown"),
        "git_sha": getattr(app.state, "git_sha", "unknown"),
        "resource_initialized": bool(repository and repository.has_local_resources()),
        "paths": {
            "project_root": str(cfg.ProjectRoot),
            "resource_root": _build_path_summary(cfg.ResourcePath),
            "character_table": _build_path_summary(cfg.ResourcePath / "gamedata" / "excel" / "character_table.json"),
            "resource_update_status": _build_path_summary(cfg.ProjectRoot / "data" / "local" / "resource-update-status.json"),
        },
        "bundle": {
            "ready": bool(repository and repository.is_ready()),
            "version": None,
            "version_date": repository.get_bundle_version_date() if repository else None,
            "operators_count": 0,
            "tokens_count": 0,
            "operator_name_index_count": 0,
            "operator_index_count": 0,
        },
        "operator_checks": [],
        "update_status": {
            "current_state": update_status.current_state,
            "last_result": update_status.last_result,
            "last_started_at": update_status.last_started_at,
            "last_finished_at": update_status.last_finished_at,
            "message": update_status.message,
            "version": update_status.version,
            "version_date": update_status.version_date,
        },
    }

    if not repository or not repository.is_ready():
        payload["operator_checks"] = [
            {
                "query": query,
                "exact_id": None,
                "search_message": "context_not_ready",
                "search_matches": [],
            }
            for query in queries
        ]
        return payload

    bundle = repository.get_bundle()
    payload["bundle"] = {
        "ready": True,
        "version": getattr(bundle, "version", None),
        "version_date": repository.get_bundle_version_date(),
        "operators_count": len(getattr(bundle, "operators", {}) or {}),
        "tokens_count": len(getattr(bundle, "tokens", {}) or {}),
        "operator_name_index_count": len(getattr(bundle, "operator_name_to_id", {}) or {}),
        "operator_index_count": len(getattr(bundle, "operator_index_to_id", {}) or {}),
    }

    operator_checks: list[dict[str, Any]] = []
    for query in queries:
        exact_id = (getattr(bundle, "operator_name_to_id", {}) or {}).get(query)
        search_message = None
        search_matches: list[dict[str, str]] = []

        try:
            search_result = search_operator(ctx, query, limit=5)
            search_payload = search_result.to_response()
            search_message = search_payload.get("message")
            search_data = search_payload.get("data") or {}
            if isinstance(search_data, dict):
                search_matches = list(search_data.get("operators") or [])
        except Exception as exc:
            search_message = f"search_error: {exc}"

        operator_checks.append(
            {
                "query": query,
                "exact_id": exact_id,
                "search_message": search_message,
                "search_matches": search_matches,
            }
        )

    payload["operator_checks"] = operator_checks
    return payload


async def _periodic_update_loop(app: FastAPI, interval_seconds: int = 15 * 60):
    log.info("后台资源刷新循环已启动: interval_seconds=%s", interval_seconds)
    while True:
        await asyncio.sleep(interval_seconds)

        ctx = getattr(app.state, "ctx", None)
        if not isinstance(ctx, AppContext):
            log.warning("跳过后台资源刷新: reason=context_not_ready")
            continue
        if not ctx.data_repository:
            log.warning("跳过后台资源刷新: reason=data_repository_missing")
            continue

        try:
            started_at = perf_counter()
            log.info("开始执行后台资源刷新")
            await ctx.data_repository.update_and_refresh()
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            log.info("后台资源刷新完成: elapsed_ms=%s", elapsed_ms)
        except asyncio.CancelledError:
            log.info("后台资源刷新循环收到取消信号")
            raise
        except Exception:
            log.exception("data_repository.update failed")


def uvicorn_main():

    cfg = load_from_disk()
    log.info(
        "准备启动 Web 服务: project_root=%s resource_path=%s base_url=%s dns_rebinding_protection=%s",
        cfg.ProjectRoot,
        cfg.ResourcePath,
        cfg.BaseUrl,
        cfg.McpDnsRebindingProtectionEnabled,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            log.info("开始初始化应用上下文")
            ctx = await build_context_from_disk(cfg)
            app.state.ctx = ctx
            app.state.code_revision = compute_service_code_revision(cfg.ProjectRoot)
            app.state.git_sha = resolve_service_git_sha(cfg.ProjectRoot)
            app.state.playwright_ready = None
            app.state.playwright_message = None

            resource_initialized = bool(
                ctx.data_repository and ctx.data_repository.has_local_resources()
            )
            log.info(
                "应用上下文初始化完成: resource_initialized=%s code_revision=%s git_sha=%s",
                resource_initialized,
                app.state.code_revision,
                app.state.git_sha,
            )

            playwright_ready, playwright_message = await probe_playwright_chromium()
            app.state.playwright_ready = playwright_ready
            app.state.playwright_message = playwright_message
            if playwright_ready:
                log.info("Playwright Chromium 运行时自检通过")
            else:
                log.warning(
                    "Playwright Chromium 运行时自检失败: %s",
                    playwright_message,
                )
        except Exception:
            log.exception("应用上下文初始化失败")
            raise

        task = asyncio.create_task(_periodic_update_loop(app, interval_seconds=15 * 60))
        log.info("后台资源刷新任务已创建")

        try:
            yield
        finally:
            log.info("Web 服务进入关闭流程")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            log.info("后台资源刷新任务已停止")

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
    register_asgi(app, cfg=cfg)
    log.info("ASGI 路由注册完成")

    @app.get("/rest/status")
    async def status():
        update_status = read_resource_update_status(cfg)
        return {
            "status": "ok",
            "code_revision": getattr(app.state, "code_revision", "unknown"),
            "git_sha": getattr(app.state, "git_sha", "unknown"),
            "resource_initialized": bool(getattr(getattr(app.state, "ctx", None), "data_repository", None) and app.state.ctx.data_repository.has_local_resources()),
            "playwright": {
                "ready": getattr(app.state, "playwright_ready", None),
                "message": getattr(app.state, "playwright_message", None),
            },
            "update_status": {
                "current_state": update_status.current_state,
                "last_result": update_status.last_result,
                "last_started_at": update_status.last_started_at,
                "last_finished_at": update_status.last_finished_at,
                "message": update_status.message,
                "version": update_status.version,
                "version_date": update_status.version_date,
            },
        }

    @app.get("/rest/resource-check")
    async def resource_check(operator_name: list[str] | None = Query(default=None)):
        return build_resource_check_payload(
            app,
            cfg=cfg,
            operator_names=operator_name,
        )

    @app.post("/rest/commands/execute")
    async def execute_command(request: Request, payload: CommandExecuteRequest):
        started_at = perf_counter()
        ctx = getattr(app.state, "ctx", None)
        if payload.command not in {"help", "exit", "config-path"} and not isinstance(ctx, AppContext):
            log.warning(
                "命令执行失败: command=%s reason=context_not_ready client=%s",
                payload.command,
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(status_code=503, detail="应用上下文未就绪")

        request_ctx = ctx
        if isinstance(ctx, AppContext):
            request_ctx = replace(
                ctx,
                prefer_local_artifact_path=(request.client is not None and request.client.host in LOCAL_REQUEST_HOSTS),
                output_format=payload.output_format,
            )

        log.info(
            "开始执行远程命令: command=%s output_format=%s prefer_local_artifact_path=%s client=%s",
            payload.command,
            payload.output_format,
            getattr(request_ctx, "prefer_local_artifact_path", False) if request_ctx is not None else False,
            request.client.host if request.client else "unknown",
        )

        try:
            result = await execute_registered_command(request_ctx, payload.command, payload.args)
        except Exception:
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            log.exception(
                "远程命令执行异常: command=%s elapsed_ms=%s client=%s",
                payload.command,
                elapsed_ms,
                request.client.host if request.client else "unknown",
            )
            raise

        elapsed_ms = int((perf_counter() - started_at) * 1000)
        response_payload = result.to_response()
        log.info(
            "远程命令执行完成: command=%s elapsed_ms=%s response_keys=%s",
            payload.command,
            elapsed_ms,
            sorted(response_payload.keys()),
        )
        return response_payload

    log.info("开始监听 HTTP 服务: host=0.0.0.0 port=9000")
    uvicorn.run(app, host="0.0.0.0", port=9000)
