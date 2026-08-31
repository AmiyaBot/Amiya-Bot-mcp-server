from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from contextlib import suppress
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any

from src.app.cache_permissions import CACHE_FILE_MODE
from src.app.card_service import CardArtifact
from src.app.config import Config


logger = logging.getLogger(__name__)

SEARCH_CARD_CACHE_TEMPLATE = "search_selection"
SEARCH_CARD_CACHE_META_FILE = "cache-meta.json"
SEARCH_CARD_CACHE_ACCESS_FILE = ".access"
SEARCH_CARD_CACHE_META_VERSION = 1
_CACHE_KEY_RE = re.compile(r"^r_[0-9a-f]{64}$")
_LOCK_STRIPES = 64


def build_search_result_cache_key(items: Iterable[Mapping[str, object]]) -> str:
    """按统一搜索的原始顺序，对全部结果 ID 做稳定编码并生成缓存键。"""
    ordered_ids = [str(item.get("id") or "") for item in items]
    canonical = json.dumps(
        ordered_ids,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"r_{digest}"


def build_search_card_fingerprint(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SearchCardCache:
    """仅用于统一搜索选择卡的有界磁盘缓存。"""

    def __init__(self, cfg: Config) -> None:
        self.root = (
            Path(cfg.ResourcePath)
            / "cache"
            / "cards"
            / SEARCH_CARD_CACHE_TEMPLATE
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock_root = self.root / ".locks"
        self.lock_root.mkdir(parents=True, exist_ok=True)

        self.max_entries = int(
            getattr(cfg, "SearchCardCacheMaxEntries", 128) or 128
        )
        self.max_bytes = int(
            getattr(cfg, "SearchCardCacheMaxBytes", 256 * 1024 * 1024)
            or 256 * 1024 * 1024
        )
        self.max_entry_bytes = int(
            getattr(cfg, "SearchCardCacheMaxEntryBytes", 16 * 1024 * 1024)
            or 16 * 1024 * 1024
        )
        self.max_entry_bytes = min(self.max_entry_bytes, self.max_bytes)

        self._entry_locks = [asyncio.Lock() for _ in range(_LOCK_STRIPES)]
        self._prune_lock = asyncio.Lock()

    async def get_or_render(
        self,
        *,
        cache_key: str,
        fingerprint: str,
        render: Callable[[], Awaitable[CardArtifact]],
    ) -> CardArtifact | None:
        """命中有效缓存，或在同一结果集合目录内重建搜索卡。"""
        self._validate_cache_key(cache_key)
        entry_lock = self._entry_locks[self._lock_index(cache_key)]

        async with entry_lock:
            lock_handle = await asyncio.to_thread(
                self._acquire_file_lock,
                self._entry_lock_path(cache_key),
            )
            try:
                cached = self._load_valid_artifact(cache_key, fingerprint)
                if cached is not None:
                    self._touch_access(cache_key)
                    return cached

                self._remove_entry(cache_key)
                artifact = await render()
                expected_dir = self._entry_dir(cache_key).resolve()
                if artifact.path.parent.resolve() != expected_dir:
                    raise RuntimeError(
                        "搜索卡片产物未写入受控缓存目录: "
                        f"expected={expected_dir} actual={artifact.path.parent}"
                    )

                self._write_metadata(
                    cache_key,
                    {
                        "meta_version": SEARCH_CARD_CACHE_META_VERSION,
                        "fingerprint": fingerprint,
                    },
                )
                self._touch_access(cache_key)
                entry_size = self._directory_size(expected_dir)
                if entry_size > self.max_entry_bytes:
                    logger.warning(
                        "搜索卡片超过单项缓存上限，已丢弃: key=%s size=%s limit=%s",
                        cache_key,
                        entry_size,
                        self.max_entry_bytes,
                    )
                    self._remove_entry(cache_key)
                    return None
            finally:
                await asyncio.to_thread(self._release_file_lock, lock_handle)

        await self.prune(exclude={cache_key})
        artifact_path = self._entry_dir(cache_key) / "artifact.png"
        if not self._is_nonempty_file(artifact_path):
            return None
        return CardArtifact(
            SEARCH_CARD_CACHE_TEMPLATE,
            cache_key,
            "png",
            artifact_path,
            mime="image/png",
        )

    async def prune(self, *, exclude: set[str] | None = None) -> None:
        """删除超出条目数或磁盘大小上限的最久未访问结果集合。"""
        excluded = exclude or set()
        async with self._prune_lock:
            lock_handle = await asyncio.to_thread(
                self._acquire_file_lock,
                self.lock_root / "prune.lock",
            )
            try:
                entries = self._scan_entries()
                total_bytes = sum(item[2] for item in entries)
                total_entries = len(entries)
                for cache_key, _access_ns, size_bytes in sorted(
                    entries,
                    key=lambda item: (item[1], item[0]),
                ):
                    if (
                        total_entries <= self.max_entries
                        and total_bytes <= self.max_bytes
                    ):
                        break
                    if cache_key in excluded:
                        continue
                    entry_lock = self._entry_locks[
                        self._lock_index(cache_key)
                    ]
                    async with entry_lock:
                        entry_handle = await asyncio.to_thread(
                            self._acquire_file_lock,
                            self._entry_lock_path(cache_key),
                        )
                        try:
                            if self._entry_dir(cache_key).exists():
                                self._remove_entry(cache_key)
                                total_entries -= 1
                                total_bytes -= size_bytes
                                logger.info(
                                    "淘汰统一搜索卡片缓存: key=%s size=%s",
                                    cache_key,
                                    size_bytes,
                                )
                        finally:
                            await asyncio.to_thread(
                                self._release_file_lock,
                                entry_handle,
                            )
            finally:
                await asyncio.to_thread(self._release_file_lock, lock_handle)

    def _load_valid_artifact(
        self,
        cache_key: str,
        fingerprint: str,
    ) -> CardArtifact | None:
        entry_dir = self._entry_dir(cache_key)
        artifact_path = entry_dir / "artifact.png"
        metadata_path = entry_dir / SEARCH_CARD_CACHE_META_FILE
        if not self._is_nonempty_file(artifact_path):
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(metadata, dict):
            return None
        if metadata.get("meta_version") != SEARCH_CARD_CACHE_META_VERSION:
            return None
        if metadata.get("fingerprint") != fingerprint:
            return None
        return CardArtifact(
            SEARCH_CARD_CACHE_TEMPLATE,
            cache_key,
            "png",
            artifact_path,
            mime="image/png",
        )

    def _scan_entries(self) -> list[tuple[str, int, int]]:
        result: list[tuple[str, int, int]] = []
        try:
            children = list(self.root.iterdir())
        except OSError:
            logger.warning("扫描统一搜索卡片缓存失败: %s", self.root, exc_info=True)
            return result

        for entry_dir in children:
            cache_key = entry_dir.name
            if not _CACHE_KEY_RE.fullmatch(cache_key):
                continue
            try:
                if entry_dir.is_symlink() or not entry_dir.is_dir():
                    continue
                access_path = entry_dir / SEARCH_CARD_CACHE_ACCESS_FILE
                access_ns = (
                    access_path.stat().st_mtime_ns
                    if access_path.is_file()
                    else entry_dir.stat().st_mtime_ns
                )
                result.append(
                    (cache_key, access_ns, self._directory_size(entry_dir))
                )
            except OSError:
                logger.warning(
                    "读取统一搜索卡片缓存条目失败: %s",
                    entry_dir,
                    exc_info=True,
                )
        return result

    def _write_metadata(self, cache_key: str, metadata: Mapping[str, Any]) -> None:
        path = self._entry_dir(cache_key) / SEARCH_CARD_CACHE_META_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".json.tmp")
        try:
            temp_path.write_text(
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            temp_path.chmod(CACHE_FILE_MODE)
            os.replace(temp_path, path)
            path.chmod(CACHE_FILE_MODE)
        finally:
            temp_path.unlink(missing_ok=True)

    def _touch_access(self, cache_key: str) -> None:
        path = self._entry_dir(cache_key) / SEARCH_CARD_CACHE_ACCESS_FILE
        try:
            path.touch(exist_ok=True)
            path.chmod(CACHE_FILE_MODE)
        except OSError:
            logger.warning("更新搜索卡片访问时间失败: %s", path, exc_info=True)

    def _remove_entry(self, cache_key: str) -> None:
        self._validate_cache_key(cache_key)
        entry_dir = self._entry_dir(cache_key)
        try:
            resolved = entry_dir.resolve()
            if not resolved.is_relative_to(self.root.resolve()):
                raise RuntimeError(f"拒绝删除搜索卡片缓存目录: {resolved}")
            if entry_dir.is_symlink():
                entry_dir.unlink(missing_ok=True)
            elif entry_dir.exists():
                shutil.rmtree(entry_dir)
        except FileNotFoundError:
            return
        except OSError:
            logger.warning("删除搜索卡片缓存失败: %s", entry_dir, exc_info=True)

    @staticmethod
    def _directory_size(path: Path) -> int:
        total = 0
        try:
            for child in path.rglob("*"):
                if child.is_file() and not child.is_symlink():
                    total += child.stat().st_size
        except OSError:
            logger.warning("统计搜索卡片缓存大小失败: %s", path, exc_info=True)
        return total

    @staticmethod
    def _is_nonempty_file(path: Path) -> bool:
        try:
            return not path.is_symlink() and path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    def _entry_dir(self, cache_key: str) -> Path:
        self._validate_cache_key(cache_key)
        return self.root / cache_key

    def _entry_lock_path(self, cache_key: str) -> Path:
        return self.lock_root / f"entry-{self._lock_index(cache_key):02d}.lock"

    @staticmethod
    def _lock_index(cache_key: str) -> int:
        return int(cache_key[2:10], 16) % _LOCK_STRIPES

    @staticmethod
    def _validate_cache_key(cache_key: str) -> None:
        if not _CACHE_KEY_RE.fullmatch(str(cache_key or "")):
            raise ValueError(f"非法统一搜索卡片缓存键: {cache_key!r}")

    @staticmethod
    def _acquire_file_lock(path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
        with suppress(OSError):
            os.chmod(path, CACHE_FILE_MODE)
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            logger.debug("文件锁不可用，退化为进程内锁: %s", path, exc_info=True)
        return handle

    @staticmethod
    def _release_file_lock(handle) -> None:
        if handle is None:
            return
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        finally:
            handle.close()
