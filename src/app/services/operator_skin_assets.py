from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from src.app.context import AppContext, get_context_resource_root
from src.app.cache_permissions import CACHE_FILE_MODE
from src.app.remote_download_manager import (
    RemoteDownloadRequest,
    RemoteDownloadResult,
    get_context_download_manager,
)
from src.domain.models.operator import Operator
from src.helpers.bundle import get_table
from src.helpers.card_urls import CHAR_SKIN_MOUNT_PATH, build_static_url

logger = logging.getLogger(__name__)

SKIN_URLS_INDEX_PATH = Path("assets") / "indexes" / "skinUrls.json"
SKIN_CACHE_PATH = Path("cache") / "char_skin"
DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_MAX_BYTES = 50 * 1024 * 1024
PRTS_ASSET_HOSTS = frozenset({"media.prts.wiki"})
SKIN_CONTENT_TYPES = frozenset(
    {"image/png", "image/webp", "image/jpeg", "application/octet-stream"}
)

_index_cache_path: Path | None = None
_index_cache_mtime_ns: int | None = None
_index_cache_payload: dict[str, dict[str, str]] = {}
_global_skin_url_cache: dict[str, str] = {}
_download_locks: dict[str, asyncio.Lock] = {}
_download_locks_guard = asyncio.Lock()


@dataclass(frozen=True)
class OperatorSkinArtifact:
    skin_id: str
    path: Path
    url: str | None

    def to_data_uri(self) -> str:
        suffix = self.path.suffix.lower()
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".webp":
            mime = "image/webp"
        elif suffix in {".jpg", ".jpeg"}:
            mime = "image/jpeg"
        else:
            mime = "application/octet-stream"

        payload = base64.b64encode(self.path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{payload}"


async def resolve_operator_skin_artifact(
    context: AppContext,
    operator: Operator,
    tables: dict,
    *,
    resource_root: Path | None = None,
) -> OperatorSkinArtifact | None:
    skin_index = _load_skin_index(resource_root or get_context_resource_root(context))
    operator_urls = skin_index.get(operator.id)
    if not isinstance(operator_urls, dict) or not operator_urls:
        return None

    selected = _select_skin_entry(operator.id, operator_urls, tables)
    if selected is None:
        return None

    skin_id, remote_url = selected
    return await _resolve_and_download(context, skin_id, remote_url)


async def resolve_skin_artifact_by_id(
    context: AppContext,
    skin_id: str,
    *,
    resource_root: Path | None = None,
) -> OperatorSkinArtifact | None:
    """按 skin_id 精确解析皮肤立绘（索引全局 skin_id 零重复，可直接全局查找）。

    供 get_operator_skins 皮肤卡片使用；索引中缺失该 skin_id 时返回 None。
    """
    normalized_skin_id = str(skin_id or "").strip()
    if not normalized_skin_id:
        return None

    _load_skin_index(resource_root or get_context_resource_root(context))
    remote_url = _global_skin_url_cache.get(normalized_skin_id)
    if not remote_url:
        logger.debug("皮肤立绘 URL 索引中不存在: %s", normalized_skin_id)
        return None

    return await _resolve_and_download(context, normalized_skin_id, remote_url)


async def _resolve_and_download(
    context: AppContext,
    skin_id: str,
    remote_url: str,
) -> OperatorSkinArtifact:
    """下载/缓存皮肤立绘并构建 artifact（resolve_operator_skin_artifact 与
    resolve_skin_artifact_by_id 的公共尾段）。"""
    cache_root = context.cfg.ResourcePath / SKIN_CACHE_PATH
    cache_root.mkdir(parents=True, exist_ok=True)

    cached_path = _find_cached_skin_path(cache_root, skin_id)
    if cached_path is None:
        lock = await _get_download_lock(skin_id)
        async with lock:
            cached_path = _find_cached_skin_path(cache_root, skin_id)
            if cached_path is None:
                downloaded = await get_context_download_manager(context).download(
                    RemoteDownloadRequest(
                        url=remote_url,
                        timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS,
                        max_bytes=DOWNLOAD_MAX_BYTES,
                        headers={"Accept": "image/png,image/webp,image/jpeg"},
                        allowed_hosts=PRTS_ASSET_HOSTS,
                        allowed_content_types=SKIN_CONTENT_TYPES,
                    )
                )
                cached_path = _cache_skin_download(
                    cache_root,
                    skin_id,
                    remote_url,
                    downloaded,
                )

    image_url = None
    try:
        image_url = build_static_url(
            cfg=context.cfg,
            relative_path=cached_path.name,
            mount_path=CHAR_SKIN_MOUNT_PATH,
        )
    except Exception:
        logger.info("构建皮肤立绘 URL 失败，已仅返回本地缓存路径", exc_info=True)

    return OperatorSkinArtifact(skin_id=skin_id, path=cached_path, url=image_url)


def _load_skin_index(resource_root: Path) -> dict[str, dict[str, str]]:
    global _index_cache_path, _index_cache_mtime_ns, _index_cache_payload

    index_path = resource_root / SKIN_URLS_INDEX_PATH
    if not index_path.exists():
        return {}

    try:
        mtime_ns = index_path.stat().st_mtime_ns
    except OSError:
        return {}

    if (
        _index_cache_path == index_path
        and _index_cache_mtime_ns == mtime_ns
        and _index_cache_payload
    ):
        return _index_cache_payload

    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("读取皮肤 URL 索引失败: %s", index_path, exc_info=True)
        return {}

    normalized: dict[str, dict[str, str]] = {}
    if isinstance(payload, dict):
        for operator_id, skin_urls in payload.items():
            if not isinstance(skin_urls, dict):
                continue
            normalized[str(operator_id)] = {
                str(skin_id): str(url)
                for skin_id, url in skin_urls.items()
                if isinstance(url, str) and url.strip()
            }

    # 全局 skin_id -> url 映射（数据验证：skin_id 全局零重复）
    _global_skin_url_cache.clear()
    for group in normalized.values():
        _global_skin_url_cache.update(group)

    _index_cache_path = index_path
    _index_cache_mtime_ns = mtime_ns
    _index_cache_payload = normalized
    return normalized


def _select_skin_entry(
    operator_id: str,
    operator_urls: dict[str, str],
    tables: dict,
) -> tuple[str, str] | None:
    # 默认优先原皮，避免与历史模板样图不一致。
    base_skin_id = f"{operator_id}#1"
    if base_skin_id in operator_urls:
        return base_skin_id, operator_urls[base_skin_id]

    preferred_skin_id = _select_preferred_skin_id(operator_id, tables)
    if preferred_skin_id and preferred_skin_id in operator_urls:
        return preferred_skin_id, operator_urls[preferred_skin_id]

    if preferred_skin_id:
        for skin_id, url in operator_urls.items():
            if skin_id.startswith(f"{operator_id}#"):
                return skin_id, url

    for skin_id, url in operator_urls.items():
        return skin_id, url
    return None


def _select_preferred_skin_id(operator_id: str, tables: dict) -> str | None:
    skin_table = get_table(tables, "skin_table", source="gamedata", default={})
    evolve_map = (skin_table.get("buildinEvolveMap") or {}).get(operator_id) or {}
    for phase in ("2", "1", "0"):
        skin_id = evolve_map.get(phase)
        if skin_id:
            return str(skin_id)

    char_skins = skin_table.get("charSkins") or {}
    candidates = [
        str(key)
        for key in char_skins.keys()
        if str(key).startswith(f"{operator_id}#")
    ]
    if not candidates:
        return None

    def _sort_key(skin_id: str) -> tuple[int, int, str]:
        suffix = skin_id.partition("#")[2]
        number = 0
        plus = 0
        digits = []
        for char in suffix:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if digits:
            number = int("".join(digits))
        if "+" in suffix:
            plus = 1
        return number, plus, skin_id

    return max(candidates, key=_sort_key)


def _find_cached_skin_path(cache_root: Path, skin_id: str) -> Path | None:
    for candidate in sorted(cache_root.glob(f"{skin_id}.*")):
        try:
            if candidate.is_symlink() or not candidate.is_file():
                continue
        except OSError:
            continue

        if _is_nonempty_readable_file(candidate):
            return candidate

        # Historical NFS cache entries may have mode 000. Repair once and
        # verify with an actual read instead of trusting st_size.
        try:
            candidate.chmod(CACHE_FILE_MODE)
        except OSError:
            pass
        if _is_nonempty_readable_file(candidate):
            return candidate

        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            logger.warning("删除无效皮肤缓存失败: %s", candidate, exc_info=True)
    return None


def _is_nonempty_readable_file(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
        with path.open("rb") as file:
            return bool(file.read(1))
    except OSError:
        return False


def _write_cache_file(temp_path: Path, target_path: Path, payload: bytes) -> None:
    try:
        temp_path.write_bytes(payload)
        temp_path.chmod(CACHE_FILE_MODE)
        os.replace(temp_path, target_path)
        # Some network filesystems do not preserve the temporary file's mode
        # across rename, so normalize the final path as well.
        target_path.chmod(CACHE_FILE_MODE)
    finally:
        temp_path.unlink(missing_ok=True)


def _cache_skin_download(
    cache_root: Path,
    skin_id: str,
    remote_url: str,
    downloaded: RemoteDownloadResult,
) -> Path:
    if not downloaded.payload:
        raise RuntimeError(f"下载干员立绘失败，返回空内容: {skin_id}")

    extension = _guess_extension(
        downloaded.content_type,
        downloaded.final_url or remote_url,
    )
    target_path = cache_root / f"{skin_id}{extension}"
    temp_path = cache_root / f".{skin_id}.download"
    _write_cache_file(temp_path, target_path, downloaded.payload)

    for candidate in cache_root.glob(f"{skin_id}.*"):
        if candidate == target_path:
            continue
        if candidate.is_file():
            candidate.unlink(missing_ok=True)

    return target_path


def _guess_extension(content_type: str | None, remote_url: str) -> str:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type == "image/png":
        return ".png"
    if normalized_type == "image/webp":
        return ".webp"
    if normalized_type == "image/jpeg":
        return ".jpg"

    parsed = urlparse(remote_url)
    remote_name = Path(parsed.path).name
    suffix = Path(remote_name).suffix.lower()
    if suffix in {".png", ".webp", ".jpg", ".jpeg"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".png"


async def _get_download_lock(skin_id: str) -> asyncio.Lock:
    async with _download_locks_guard:
        lock = _download_locks.get(skin_id)
        if lock is None:
            lock = asyncio.Lock()
            _download_locks[skin_id] = lock
        return lock
