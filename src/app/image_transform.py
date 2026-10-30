# src/app/image_transform.py
"""静态图片的按需缩放（REQ-mcp-image-serving P1-1）。

用法：在既有 URL 后追加 `?w=1080&q=85`。

- `w`：目标宽度（等比缩放，仅缩小不放大），合法区间 16–2048；
- `q`：WEBP 质量，合法区间 1–100，默认 85；
- 未带参数、参数非法或请求 Range 分片时，完全走原生 StaticFiles，行为不变。

产物落盘在 `cache/image_thumbs`，按「源路径 + mtime + 尺寸参数」哈希命名，
同一张卡片只在首次请求时解码一次。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import stat as stat_module
from pathlib import Path
from urllib.parse import parse_qs

import anyio
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

TRANSFORM_CACHE_DIRNAME = Path("cache") / "image_thumbs"
DEFAULT_MAX_WIDTH = 2048
DEFAULT_QUALITY = 85
MIN_WIDTH = 16
OUTPUT_MEDIA_TYPE = "image/webp"

# Pillow 缺失时不能让整个服务起不来：顶层软导入，缺失则 `?w=` 参数退化为忽略。
try:  # pragma: no cover - 依赖安装状态
    from PIL import Image as _PILImage
except ModuleNotFoundError:  # pragma: no cover
    _PILImage = None

_pillow_warning_emitted = False

_render_locks: dict[str, asyncio.Lock] = {}
_render_locks_guard = asyncio.Lock()


def _warn_pillow_missing_once() -> None:
    """Pillow 缺失只报一次，避免每个 `?w=` 请求都刷一整段 traceback。"""
    global _pillow_warning_emitted
    if _pillow_warning_emitted:
        return
    _pillow_warning_emitted = True
    logger.error(
        "图像缩放不可用：缺少 Pillow，`?w=`/`?q=` 参数将被忽略并直接返回原图。"
        "请安装 pillow（requirements.txt 已声明）。"
    )


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def parse_transform_params(query_string: bytes) -> tuple[int, int] | None:
    """解析 `?w=&q=`；无有效 `w` 时返回 None（表示不做变换）。"""
    if not query_string:
        return None

    try:
        params = parse_qs(query_string.decode("latin-1"), keep_blank_values=False)
    except UnicodeDecodeError:
        return None

    raw_width = params.get("w", [None])[0]
    if not raw_width:
        return None

    try:
        width = int(raw_width)
    except (TypeError, ValueError):
        return None

    raw_quality = params.get("q", [None])[0]
    try:
        quality = int(raw_quality) if raw_quality else DEFAULT_QUALITY
    except (TypeError, ValueError):
        quality = DEFAULT_QUALITY

    return _clamp(width, MIN_WIDTH, DEFAULT_MAX_WIDTH), _clamp(quality, 1, 100)


def _transform_cache_key(
    source_path: str,
    stat_result: os.stat_result,
    width: int,
    quality: int,
) -> str:
    raw = f"{source_path}|{stat_result.st_mtime_ns}|{stat_result.st_size}|{width}|{quality}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


async def _get_render_lock(cache_key: str) -> asyncio.Lock:
    async with _render_locks_guard:
        lock = _render_locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            _render_locks[cache_key] = lock
        return lock


def _render_resized(source_path: str, target_path: Path, width: int, quality: int) -> None:
    """同步渲染：解码源图 → 等比缩小 → 输出 WEBP。在线程池中执行。"""
    Image = _PILImage
    if Image is None:  # pragma: no cover - get_response 已提前拦截
        raise RuntimeError("Pillow 不可用，无法缩放图片")

    temp_path = target_path.with_name(f".{target_path.name}.tmp")
    try:
        with Image.open(source_path) as image:
            image.load()
            if image.mode not in ("RGB", "RGBA"):
                has_alpha = "A" in image.getbands() or "transparency" in image.info
                image = image.convert("RGBA" if has_alpha else "RGB")

            if image.width > width:
                height = max(1, round(image.height * width / image.width))
                image = image.resize((width, height), Image.LANCZOS)

            image.save(temp_path, format="WEBP", quality=quality, method=4)
        os.replace(temp_path, target_path)
    finally:
        temp_path.unlink(missing_ok=True)


class TransformableStaticFiles(StaticFiles):
    """在 StaticFiles 之上支持 `?w=&q=`，其余行为完全委托父类。"""

    def __init__(
        self,
        *,
        directory: str,
        cache_directory: Path,
        **kwargs,
    ) -> None:
        super().__init__(directory=directory, **kwargs)
        self.cache_directory = cache_directory

    async def get_response(self, path: str, scope):
        params = parse_transform_params(scope.get("query_string", b""))
        if params is None or scope.get("method") not in ("GET", "HEAD"):
            return await super().get_response(path, scope)

        if _PILImage is None:
            _warn_pillow_missing_once()
            return await super().get_response(path, scope)

        width, quality = params

        try:
            full_path, stat_result = await anyio.to_thread.run_sync(self.lookup_path, path)
        except PermissionError:
            raise HTTPException(status_code=401)
        except OSError:
            return await super().get_response(path, scope)

        if not stat_result or not stat_module.S_ISREG(stat_result.st_mode):
            return await super().get_response(path, scope)

        cache_key = _transform_cache_key(full_path, stat_result, width, quality)
        target_path = self.cache_directory / f"{cache_key}.webp"

        if not target_path.is_file():
            lock = await _get_render_lock(cache_key)
            async with lock:
                if not target_path.is_file():
                    self.cache_directory.mkdir(parents=True, exist_ok=True)
                    try:
                        await anyio.to_thread.run_sync(
                            _render_resized,
                            full_path,
                            target_path,
                            width,
                            quality,
                        )
                    except Exception:
                        # 缩放失败不应让请求失败，退回原图（仍是正确内容，只是更大）。
                        logger.warning("图片缩放失败，回退原图: %s", full_path, exc_info=True)
                        return await super().get_response(path, scope)

        return FileResponse(target_path, media_type=OUTPUT_MEDIA_TYPE)
