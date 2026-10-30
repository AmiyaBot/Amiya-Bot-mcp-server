# src/app/static_media.py
"""静态媒体响应的 MIME 修正与缓存头注入。

需求来源：REQ-mcp-image-serving（AmiyaBot-Stellar，2026-10-28）

- P0-1（阻断级）：`.webp` 在运行时 mimetypes 表中缺失，Starlette `FileResponse`
  的 `media_type = guess_type(...)[0] or "text/plain"` 会回落成 `text/plain`，
  机器人侧只接受 `image/*`，判定 `not_image` 后静默丢图。
- P0-3：`StaticFiles` 不设置 `Cache-Control`，同一张卡片图每次都要重新拉取。
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from typing import Iterable, Sequence

from starlette.datastructures import MutableHeaders

from src.helpers.card_urls import (
    CHAR_SKIN_MOUNT_PATH,
    DEFAULT_MOUNT_PATH,
    GAME_ASSETS_MOUNT_PATH,
    INTEGRATED_STRATEGY_COLLECTIBLE_ICON_MOUNT_PATH,
)

# Python 3.12 的 mimetypes 内置表与 python:3.12-slim 镜像均不含这些扩展名。
# 缺失时 Starlette 会回落 text/plain，必须显式补齐。
_EXTRA_MIME_TYPES: dict[str, str] = {
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".jxl": "image/jxl",
    ".jp2": "image/jp2",
}

# 仅对成功类响应注入缓存头：404/500 若被缓存会把瞬时故障固化成长期错误。
CACHEABLE_RESPONSE_STATUSES = frozenset({200, 206, 304})

# 卡片 key 含资源版本（如 ade7aa2:card-v21），立绘 filename 即 skin_id 且内容稳定，
# 两者都可用 immutable；/game-assets 的 URL 不含版本，长缓存会在发布切换后读到旧图。
IMMUTABLE_CACHE_CONTROL = "public, max-age=86400, immutable"
REVALIDATE_CACHE_CONTROL = "public, max-age=3600"


@dataclass(frozen=True)
class StaticCachePolicy:
    mount_path: str
    cache_control: str


_installed = False


def install_static_mime_types() -> None:
    """补齐运行环境缺失的图片 MIME 映射（幂等）。"""
    global _installed
    if _installed:
        return
    for extension, mime_type in _EXTRA_MIME_TYPES.items():
        mimetypes.add_type(mime_type, extension)
    _installed = True


def default_static_cache_policies() -> tuple[StaticCachePolicy, ...]:
    return (
        StaticCachePolicy(DEFAULT_MOUNT_PATH, IMMUTABLE_CACHE_CONTROL),
        StaticCachePolicy(CHAR_SKIN_MOUNT_PATH, IMMUTABLE_CACHE_CONTROL),
        StaticCachePolicy(
            INTEGRATED_STRATEGY_COLLECTIBLE_ICON_MOUNT_PATH,
            IMMUTABLE_CACHE_CONTROL,
        ),
        StaticCachePolicy(GAME_ASSETS_MOUNT_PATH, REVALIDATE_CACHE_CONTROL),
    )


class StaticCacheControlMiddleware:
    """为静态媒体挂载注入 Cache-Control（纯 ASGI，保留 Range/304 语义）。"""

    def __init__(
        self,
        app,
        *,
        policies: Iterable[StaticCachePolicy] | None = None,
    ) -> None:
        self.app = app
        self._policies: Sequence[StaticCachePolicy] = tuple(
            sorted(
                policies if policies is not None else default_static_cache_policies(),
                key=lambda item: len(item.mount_path),
                reverse=True,
            )
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        cache_control = self._cache_control_for(scope.get("path", ""))
        if cache_control is None:
            await self.app(scope, receive, send)
            return

        async def send_with_cache_control(message) -> None:
            if (
                message["type"] == "http.response.start"
                and message.get("status") in CACHEABLE_RESPONSE_STATUSES
            ):
                headers = MutableHeaders(scope=message)
                if "cache-control" not in headers:
                    headers["cache-control"] = cache_control
            await send(message)

        await self.app(scope, receive, send_with_cache_control)

    def _cache_control_for(self, path: str) -> str | None:
        for policy in self._policies:
            mount_path = policy.mount_path
            if path == mount_path or path.startswith(mount_path + "/"):
                return policy.cache_control
        return None
