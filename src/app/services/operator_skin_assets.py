from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from src.app.context import AppContext
from src.domain.models.operator import Operator
from src.helpers.bundle import get_table
from src.helpers.card_urls import CHAR_SKIN_MOUNT_PATH, build_static_url

logger = logging.getLogger(__name__)

SKIN_URLS_INDEX_PATH = Path("assets") / "indexes" / "skinUrls.json"
SKIN_CACHE_PATH = Path("cache") / "char_skin"
DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_USER_AGENT = "AmiyaBotMCPServer/0.1"

_index_cache_path: Path | None = None
_index_cache_mtime_ns: int | None = None
_index_cache_payload: dict[str, dict[str, str]] = {}
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
) -> OperatorSkinArtifact | None:
    skin_index = _load_skin_index(context.cfg.ResourcePath)
    operator_urls = skin_index.get(operator.id)
    if not isinstance(operator_urls, dict) or not operator_urls:
        return None

    selected = _select_skin_entry(operator.id, operator_urls, tables)
    if selected is None:
        return None

    skin_id, remote_url = selected
    cache_root = context.cfg.ResourcePath / SKIN_CACHE_PATH
    cache_root.mkdir(parents=True, exist_ok=True)

    cached_path = _find_cached_skin_path(cache_root, skin_id)
    if cached_path is None:
        lock = await _get_download_lock(skin_id)
        async with lock:
            cached_path = _find_cached_skin_path(cache_root, skin_id)
            if cached_path is None:
                cached_path = await asyncio.to_thread(
                    _download_skin_file,
                    cache_root,
                    skin_id,
                    remote_url,
                )

    image_url = None
    try:
        image_url = build_static_url(
            cfg=context.cfg,
            relative_path=cached_path.name,
            mount_path=CHAR_SKIN_MOUNT_PATH,
        )
    except Exception:
        logger.info("构建干员立绘 URL 失败，已仅返回本地缓存路径", exc_info=True)

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
        if candidate.is_file():
            try:
                if candidate.stat().st_size > 0:
                    return candidate
            except OSError:
                continue
    return None


def _download_skin_file(cache_root: Path, skin_id: str, remote_url: str) -> Path:
    encoded_url = _encode_url_path(remote_url)
    request = Request(encoded_url, headers={"User-Agent": DOWNLOAD_USER_AGENT})
    with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        payload = response.read()
        content_type = response.headers.get_content_type()

    if not payload:
        raise RuntimeError(f"下载干员立绘失败，返回空内容: {skin_id}")

    extension = _guess_extension(content_type, remote_url)
    target_path = cache_root / f"{skin_id}{extension}"
    temp_path = cache_root / f".{skin_id}.download"
    temp_path.write_bytes(payload)

    try:
        for candidate in cache_root.glob(f"{skin_id}.*"):
            if candidate == target_path:
                continue
            if candidate.is_file():
                candidate.unlink(missing_ok=True)
        temp_path.replace(target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    return target_path


def _encode_url_path(remote_url: str) -> str:
    split_result = urlsplit(remote_url)
    encoded_path = quote(split_result.path, safe="/%:@+$,;=-._~!()*[]")
    return urlunsplit(
        (
            split_result.scheme,
            split_result.netloc,
            encoded_path,
            split_result.query,
            split_result.fragment,
        )
    )


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