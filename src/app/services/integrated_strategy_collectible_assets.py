from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError

from src.app.cache_permissions import CACHE_FILE_MODE
from src.app.context import AppContext
from src.app.remote_download_manager import (
    RemoteDownloadRequest,
    get_context_download_manager,
)
from src.helpers.card_urls import (
    INTEGRATED_STRATEGY_COLLECTIBLE_ICON_MOUNT_PATH,
    build_static_url,
)


logger = logging.getLogger(__name__)

COLLECTIBLE_ICON_CACHE_PATH = (
    Path("cache") / "integrated_strategy_collectible_icons"
)
COLLECTIBLE_ICON_BASE_URL = (
    "https://torappu.prts.wiki/assets/roguelike_topic_itempic/"
)
DOWNLOAD_TIMEOUT_SECONDS = 10
DOWNLOAD_MAX_BYTES = 5 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PRTS_ASSET_HOSTS = frozenset({"torappu.prts.wiki"})
_SAFE_ICON_ID = re.compile(r"^[A-Za-z0-9_.-]+$")

_download_locks: dict[str, asyncio.Lock] = {}
_download_locks_guard = asyncio.Lock()
_missing_icon_ids: set[str] = set()


@dataclass(frozen=True)
class IntegratedStrategyCollectibleIconArtifact:
    icon_id: str
    path: Path
    url: str | None

    def to_data_uri(self) -> str:
        payload = base64.b64encode(self.path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{payload}"


def build_collectible_icon_source_url(icon_id: str) -> str | None:
    normalized_icon_id = _normalize_icon_id(icon_id)
    if normalized_icon_id is None:
        return None
    return f"{COLLECTIBLE_ICON_BASE_URL}{normalized_icon_id}.png"


async def resolve_collectible_icon_artifact(
    context: AppContext,
    icon_id: str,
) -> IntegratedStrategyCollectibleIconArtifact | None:
    """按 iconId 从 PRTS 资源站下载藏品图标并持久化缓存。"""
    normalized_icon_id = _normalize_icon_id(icon_id)
    if normalized_icon_id is None:
        logger.warning("拒绝非法集成战略藏品 iconId: %r", icon_id)
        return None

    cache_root = context.cfg.ResourcePath / COLLECTIBLE_ICON_CACHE_PATH
    cache_root.mkdir(parents=True, exist_ok=True)
    cached_path = _find_cached_icon_path(cache_root, normalized_icon_id)

    if cached_path is None and normalized_icon_id not in _missing_icon_ids:
        lock = await _get_download_lock(normalized_icon_id)
        async with lock:
            cached_path = _find_cached_icon_path(cache_root, normalized_icon_id)
            if cached_path is None and normalized_icon_id not in _missing_icon_ids:
                try:
                    remote_url = build_collectible_icon_source_url(
                        normalized_icon_id
                    )
                    if remote_url is None:
                        return None
                    downloaded = await get_context_download_manager(context).download(
                        RemoteDownloadRequest(
                            url=remote_url,
                            timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS,
                            max_bytes=DOWNLOAD_MAX_BYTES,
                            headers={"Accept": "image/png"},
                            allowed_hosts=PRTS_ASSET_HOSTS,
                            allowed_content_types=frozenset(
                                {"image/png", "application/octet-stream"}
                            ),
                        )
                    )
                    cached_path = _cache_collectible_icon(
                        cache_root,
                        normalized_icon_id,
                        downloaded.payload,
                    )
                except HTTPError as exc:
                    if exc.code == 404:
                        _missing_icon_ids.add(normalized_icon_id)
                        logger.info(
                            "PRTS 不存在集成战略藏品图标: icon_id=%s",
                            normalized_icon_id,
                        )
                    else:
                        logger.warning(
                            "下载集成战略藏品图标失败: icon_id=%s status=%s",
                            normalized_icon_id,
                            exc.code,
                            exc_info=True,
                        )
                    return None
                except (OSError, RuntimeError, TimeoutError, URLError):
                    logger.warning(
                        "下载集成战略藏品图标失败: icon_id=%s",
                        normalized_icon_id,
                        exc_info=True,
                    )
                    return None

    if cached_path is None:
        return None

    image_url = None
    try:
        image_url = build_static_url(
            cfg=context.cfg,
            relative_path=cached_path.name,
            mount_path=INTEGRATED_STRATEGY_COLLECTIBLE_ICON_MOUNT_PATH,
        )
    except Exception:
        logger.info(
            "构建集成战略藏品图标 URL 失败，已仅保留本地缓存: icon_id=%s",
            normalized_icon_id,
            exc_info=True,
        )

    return IntegratedStrategyCollectibleIconArtifact(
        icon_id=normalized_icon_id,
        path=cached_path,
        url=image_url,
    )


async def attach_collectible_icon_artifacts(
    context: AppContext,
    response_payload: dict,
) -> dict[str, IntegratedStrategyCollectibleIconArtifact]:
    """为搜索藏品附加 URL，并返回可直接用于选择卡的图标产物。"""
    artifacts: dict[str, IntegratedStrategyCollectibleIconArtifact] = {}
    data = response_payload.get("data")
    if not isinstance(data, dict):
        return artifacts
    items = data.get("items")
    if not isinstance(items, list):
        return artifacts

    async def attach_one(item: object) -> None:
        if not isinstance(item, dict) or item.get("type") != "集成战略藏品":
            return
        icon_id = str(item.get("icon_id") or "").strip()
        if not icon_id:
            return
        try:
            artifact = await resolve_collectible_icon_artifact(context, icon_id)
        except Exception:
            # 图标是搜索结果的可选增强；缓存目录不可写等异常不能使结构化查询失败。
            logger.warning(
                "准备集成战略藏品图标失败，已保留无图搜索结果: icon_id=%s",
                icon_id,
                exc_info=True,
            )
            return
        if artifact is None:
            return
        item_id = str(item.get("id") or "").strip()
        if item_id:
            artifacts[item_id] = artifact
        if artifact.url:
            item["icon_url"] = artifact.url
        if context.prefer_local_artifact_path:
            item["icon_path"] = str(artifact.path)

    await asyncio.gather(*(attach_one(item) for item in items))
    return artifacts


def _normalize_icon_id(icon_id: str) -> str | None:
    normalized = str(icon_id or "").strip()
    if not normalized or not _SAFE_ICON_ID.fullmatch(normalized):
        return None
    return normalized


def _find_cached_icon_path(cache_root: Path, icon_id: str) -> Path | None:
    path = cache_root / f"{icon_id}.png"
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if _is_valid_png_file(path):
            return path
        path.chmod(CACHE_FILE_MODE)
        if _is_valid_png_file(path):
            return path
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("检查集成战略藏品图标缓存失败: %s", path, exc_info=True)
    return None


def _is_valid_png_file(path: Path) -> bool:
    try:
        if path.stat().st_size <= len(PNG_SIGNATURE):
            return False
        with path.open("rb") as file:
            return file.read(len(PNG_SIGNATURE)) == PNG_SIGNATURE
    except OSError:
        return False


def _cache_collectible_icon(cache_root: Path, icon_id: str, payload: bytes) -> Path:
    if not payload.startswith(PNG_SIGNATURE):
        raise RuntimeError(f"下载藏品图标缺少 PNG 文件签名: {icon_id}")

    target_path = cache_root / f"{icon_id}.png"
    temp_path = cache_root / f".{icon_id}.download"
    _write_cache_file(temp_path, target_path, payload)
    return target_path


def _write_cache_file(temp_path: Path, target_path: Path, payload: bytes) -> None:
    try:
        temp_path.write_bytes(payload)
        temp_path.chmod(CACHE_FILE_MODE)
        os.replace(temp_path, target_path)
        target_path.chmod(CACHE_FILE_MODE)
    finally:
        temp_path.unlink(missing_ok=True)


async def _get_download_lock(icon_id: str) -> asyncio.Lock:
    async with _download_locks_guard:
        lock = _download_locks.get(icon_id)
        if lock is None:
            lock = asyncio.Lock()
            _download_locks[icon_id] = lock
        return lock
