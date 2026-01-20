from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.app.transformers.types import Transformer

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
            browser = await p.chromium.launch(headless=headless, args=chromium_args)
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
                return png_bytes
            finally:
                await browser.close()
