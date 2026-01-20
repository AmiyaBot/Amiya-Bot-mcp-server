from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import logging
from jinja2 import TemplateNotFound

from src.app.config import Config
from src.app.renderers.jinja_html_renderer import JinjaHtmlRenderer
from src.app.renderers.jinja_json_renderer import JinjaJsonRenderer
from src.app.renderers.jinja_template_loader import JinjaTemplateLoader
from src.app.renderers.jinja_text_renderer import JinjaTextRenderer
from src.app.renderers.types import Renderer
from src.app.transformers.types import Transformer
from src.app.transformers.html_to_png_transformer import HTMLToPNGTransformer
from src.domain.types import QueryResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CardArtifact:
    template: str
    payload_key: str
    format: str  # "png" | "html" | "txt" | "json"
    path: Path
    mime: str | None = None

    def exists(self) -> bool:
        return self.path.exists()

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.path.read_text(encoding=encoding)


def _deep_merge(base: dict, override: dict) -> dict:
    """
    深合并配置：用于 viewport 等嵌套 dict 的覆写。
    override 优先。
    """
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class CardService:
    """
    需求对齐版（使用 HTMLToPNGTransformer）：

    1) PNG 必须由 HTML 渲染而来；缺 html 模板 => png 必须报错。
    2) 产物统一落盘：png/html/txt/json 都是磁盘缓存产物。
       - 请求 png 时，会同时确保 html artifact 生成并落盘（复用缓存，避免重复渲染）。
    3) 模板不一定同时具备所有格式：
       - 只有当用户请求某个格式时，才要求对应模板存在；
       - 未请求的格式，即使模板缺失，也绝不报错、绝不尝试加载。
       - 例外：请求 png 等价于“也请求 html”，因为 png 依赖 html。
    4) 未知 format 直接报错。
    """

    def __init__(self, cfg: Config, *, html_to_png: Transformer | None = None):
        templates_root = cfg.ProjectRoot / "data" / "templates"
        loader = JinjaTemplateLoader(str(templates_root))

        self.text_renderer: Renderer = JinjaTextRenderer(loader)
        self.json_renderer: Renderer = JinjaJsonRenderer(loader)
        self.html_renderer: Renderer = JinjaHtmlRenderer(loader)

        self.html_to_png: Transformer = html_to_png or HTMLToPNGTransformer()

        self.cache_root: Path = cfg.ResourcePath / "cache" / "cards"
        self.cache_root.mkdir(parents=True, exist_ok=True)

        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def get(
        self,
        *,
        template: str,
        payload_key: str,
        payload: object,
        params: dict | None = None,
        format: str = "png",
    ) -> CardArtifact:
        fmt = format.lower().strip().lstrip(".")
        allowed = ("png", "html", "txt", "json")
        if fmt not in allowed:
            raise ValueError(f"Unsupported format: {format}. Must be one of {allowed}")

        params = params or {}
        qr = self._ensure_query_result(payload)

        # png：先确保 html 落盘并复用
        if fmt == "png":
            html_artifact = await self.get(
                template=template,
                payload_key=payload_key,
                payload=qr,
                params=params,
                format="html",
            )
            return await self._get_png_from_html(
                template=template,
                payload_key=payload_key,
                html_artifact=html_artifact,
                qr=qr,
                params=params,
            )

        return await self._get_single_non_png(
            template=template,
            payload_key=payload_key,
            qr=qr,
            format=fmt,
        )

    async def get_many(
        self,
        *,
        template: str,
        payload_key: str,
        payload: object,
        params: dict | None = None,
        formats: list[str] | None = None,
    ) -> dict[str, CardArtifact]:
        formats = formats or ["png", "html"]
        out: dict[str, CardArtifact] = {}
        for f in formats:
            out[f] = await self.get(
                template=template,
                payload_key=payload_key,
                payload=payload,
                params=params,
                format=f,
            )
        return out

    # ----------------- core implementations -----------------

    async def _get_single_non_png(
        self,
        *,
        template: str,
        payload_key: str,
        qr: QueryResult,
        format: str,  # "html" | "txt" | "json"
    ) -> CardArtifact:
        out_dir = self.cache_root / template / payload_key
        out_path = out_dir / f"artifact.{format}"

        # 快速命中
        if out_path.exists():
            try:
                if out_path.stat().st_size > 0:
                    return CardArtifact(template, payload_key, format, out_path)
            except FileNotFoundError:
                pass

        lock_key = f"{template}:{payload_key}:{format}"
        lock = await self._get_lock(lock_key)

        async with lock:
            # double-check
            if out_path.exists():
                try:
                    if out_path.stat().st_size > 0:
                        return CardArtifact(template, payload_key, format, out_path)
                except FileNotFoundError:
                    pass

            out_dir.mkdir(parents=True, exist_ok=True)

            if format == "html":
                ro = self.html_renderer.render(template, qr)  # 缺模板 => TemplateNotFound（请求才要求存在）
                await self._atomic_write_text(out_path, ro.payload, encoding="utf-8")
                return CardArtifact(template, payload_key, format, out_path, mime=ro.mime)

            if format == "txt":
                ro = self.text_renderer.render(template, qr)
                await self._atomic_write_text(out_path, ro.payload, encoding="utf-8")
                return CardArtifact(template, payload_key, format, out_path, mime=ro.mime)

            if format == "json":
                ro = self.json_renderer.render(template, qr)
                # 注意：你的 JinjaJsonRenderer 返回 payload 为 dict/list（不是字符串）
                json_text = json.dumps(ro.payload, ensure_ascii=False, indent=2)
                await self._atomic_write_text(out_path, json_text, encoding="utf-8")
                return CardArtifact(template, payload_key, format, out_path, mime=ro.mime)

            raise ValueError(f"Unsupported non-png format: {format}")

    async def _get_png_from_html(
        self,
        *,
        template: str,
        payload_key: str,
        html_artifact: CardArtifact,
        qr: QueryResult,
        params: dict,
    ) -> CardArtifact:
        out_dir = self.cache_root / template / payload_key
        out_path = out_dir / "artifact.png"

        # 快速命中
        if out_path.exists():
            try:
                if out_path.stat().st_size > 0:
                    return CardArtifact(template, payload_key, "png", out_path, mime="image/png")
            except FileNotFoundError:
                pass

        lock_key = f"{template}:{payload_key}:png"
        lock = await self._get_lock(lock_key)

        async with lock:
            # double-check
            if out_path.exists():
                try:
                    if out_path.stat().st_size > 0:
                        return CardArtifact(template, payload_key, "png", out_path, mime="image/png")
                except FileNotFoundError:
                    pass

            out_dir.mkdir(parents=True, exist_ok=True)

            # png 配置：json 模板可选，缺失静默
            render_cfg = self._load_png_render_cfg_optional(template, qr)
            merged_cfg = _deep_merge(render_cfg, params or {})

            html = html_artifact.read_text(encoding="utf-8")

            png_bytes = await self.html_to_png.transform(input=html, cfg=merged_cfg)
            if not isinstance(png_bytes, (bytes, bytearray)):
                raise TypeError(
                    f"HTMLToPNGTransformer must return bytes, got {type(png_bytes)}"
                )

            await self._atomic_write_bytes(out_path, bytes(png_bytes))
            return CardArtifact(template, payload_key, "png", out_path, mime="image/png")

    # ----------------- internals -----------------

    async def _get_lock(self, key: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    def _ensure_query_result(self, payload: object) -> QueryResult:
        if isinstance(payload, QueryResult):
            return payload
        if isinstance(payload, dict):
            return QueryResult(type="", key="", title="", data=payload)
        return QueryResult(type="", key="", title="", data={"payload": payload})

    def _load_png_render_cfg_optional(self, template: str, qr: QueryResult) -> dict[str, Any]:
        """
        png 渲染配置来源：尝试用 json 模板渲染出配置 dict。
        - json 模板缺失：静默返回 {}
        - json 不是 dict 或解析失败：静默返回 {}
        只有在请求 png 时才会调用（满足“未请求不报错”）。
        """
        try:
            ro = self.json_renderer.render(template, qr)
        except TemplateNotFound:
            return {}

        payload = ro.payload
        if payload is None:
            return {}
        return payload if isinstance(payload, dict) else {}

    async def _atomic_write_text(self, path: Path, content: str, *, encoding: str = "utf-8") -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding=encoding)
        os.replace(tmp, path)

    async def _atomic_write_bytes(self, path: Path, content: bytes) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(content)
        os.replace(tmp, path)
