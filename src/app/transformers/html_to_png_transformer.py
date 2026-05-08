from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.app.transformers.types import Transformer

logger = logging.getLogger(__name__)


async def probe_playwright_chromium(
    *,
    headless: bool = True,
    chromium_args: list[str] | None = None,
) -> tuple[bool, str | None]:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        return False, f"Playwright 不可用: {exc}"

    launch_args = chromium_args or []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless, args=launch_args)
            await browser.close()
    except Exception as exc:
        return False, str(exc)

    return True, None

class HTMLToPNGTransformer(Transformer):
    """
    使用 Playwright 把 HTML 字符串渲染为 PNG bytes。

    cfg 常用字段（都可选）：
    - viewport: {"width": 900, "height": 520, "deviceScaleFactor": 2}
    - full_page: true/false
    - wait_until: "load" | "domcontentloaded" | "networkidle"
    - extra_wait_ms: 0..n
    - transparent: true/false
    - chromium_args: ["--font-render-hinting=medium", ...]  # 可选
    - headless: true/false  # 可选
    """

    input_mime = "text/html"
    output_mime = "image/png"

    async def transform(self, *, input: Any, cfg: Dict[str, Any] | None = None) -> bytes:
        if not isinstance(input, str):
            raise TypeError(f"HTMLToPNGTransformer expects input=str, got {type(input)}")

        cfg = cfg or {}

        viewport = cfg.get("viewport") or {"width": 900, "height": 520}
        full_page = bool(cfg.get("full_page", False))
        wait_until = cfg.get("wait_until", "networkidle")
        extra_wait_ms = int(cfg.get("extra_wait_ms", 0))
        transparent = bool(cfg.get("transparent", False))

        chromium_args = cfg.get("chromium_args") or []
        headless = cfg.get("headless", True)

        try:
            from playwright.async_api import async_playwright
        except Exception as e:
            raise RuntimeError(
                "Playwright 不可用，无法渲染 PNG。请安装 playwright 并执行 playwright install。"
            ) from e

        async with async_playwright() as p:
            try:
                logger.info(
                    "开始启动 Playwright Chromium: headless=%s viewport=%s full_page=%s wait_until=%s extra_wait_ms=%s chromium_args=%s",
                    headless,
                    viewport,
                    full_page,
                    wait_until,
                    extra_wait_ms,
                    chromium_args,
                )
                browser = await p.chromium.launch(headless=headless, args=chromium_args)
            except Exception:
                logger.exception(
                    "启动 Playwright Chromium 失败，无法渲染 PNG。请检查浏览器安装和系统依赖是否完整。"
                )
                raise
            try:
                page = await browser.new_page(viewport=viewport)  # type: ignore
                await page.set_content(input, wait_until=wait_until)

                if extra_wait_ms > 0:
                    await page.wait_for_timeout(extra_wait_ms)

                png_bytes = await page.screenshot(
                    full_page=full_page,
                    type="png",
                    omit_background=transparent,
                )
                logger.info("Playwright Chromium 渲染 PNG 成功: bytes=%s", len(png_bytes))
                return png_bytes
            finally:
                await browser.close()
