from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import logging
import time
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from src.app.remote_download_manager import DEFAULT_REMOTE_DOWNLOAD_USER_AGENT


logger = logging.getLogger(__name__)

SEARCH_ALIAS_SOURCE_URL = (
    "http://106.52.139.57:8000/replace/getGlobalReplace"
)
SEARCH_ALIAS_SYNC_INTERVAL_SECONDS = 60 * 60
SEARCH_ALIAS_DOWNLOAD_TIMEOUT_SECONDS = 15.0
SEARCH_ALIAS_DOWNLOAD_MAX_BYTES = 2 * 1024 * 1024
SEARCH_ALIAS_MAX_RECORDS = 10_000
SEARCH_ALIAS_MAX_TEXT_LENGTH = 128

_LEGACY_ALIAS_HOST = "106.52.139.57"
_LEGACY_ALIAS_PORT = 8000
_LEGACY_ALIAS_PATH = "/replace/getGlobalReplace"
_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "text/json",
        "text/plain",
    }
)


@dataclass(frozen=True, slots=True)
class SearchAliasSnapshot:
    """一次完整同步得到的只读别名快照。"""

    alias_to_origins: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    synced_at: float | None = None
    source_record_count: int = 0

    @classmethod
    def empty(cls) -> "SearchAliasSnapshot":
        return cls()


@dataclass(frozen=True, slots=True)
class SearchAliasSyncResult:
    ok: bool
    alias_count: int
    source_record_count: int
    message: str


class SearchAliasRepository:
    """定期拉取旧 AmiyaBot 全局替换表并原子发布只读快照。"""

    def __init__(
        self,
        *,
        source_url: str = SEARCH_ALIAS_SOURCE_URL,
        timeout_seconds: float = SEARCH_ALIAS_DOWNLOAD_TIMEOUT_SECONDS,
        max_bytes: int = SEARCH_ALIAS_DOWNLOAD_MAX_BYTES,
    ) -> None:
        _validate_source_url(source_url)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")
        if max_bytes <= 0:
            raise ValueError("max_bytes 必须大于 0")

        self.source_url = source_url
        self.timeout_seconds = float(timeout_seconds)
        self.max_bytes = int(max_bytes)
        self._snapshot = SearchAliasSnapshot.empty()
        self._sync_lock = asyncio.Lock()

    def get_snapshot(self) -> SearchAliasSnapshot:
        return self._snapshot

    async def sync(self) -> SearchAliasSyncResult:
        """下载并发布完整快照；任何失败都保留上一版数据。"""
        async with self._sync_lock:
            try:
                payload = await asyncio.to_thread(self._download)
                alias_to_origins, source_record_count = _parse_alias_payload(
                    payload
                )
                if not alias_to_origins:
                    raise ValueError("别名接口未返回任何有效记录")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                current = self._snapshot
                logger.warning(
                    "同步统一搜索别名失败，继续使用上一版快照: aliases=%s error=%s",
                    len(current.alias_to_origins),
                    exc,
                    exc_info=True,
                )
                return SearchAliasSyncResult(
                    ok=False,
                    alias_count=len(current.alias_to_origins),
                    source_record_count=current.source_record_count,
                    message=str(exc),
                )

            snapshot = SearchAliasSnapshot(
                alias_to_origins=MappingProxyType(alias_to_origins),
                synced_at=time.time(),
                source_record_count=source_record_count,
            )
            # 完整解析后再切换引用，搜索请求只会看到旧或新快照之一。
            self._snapshot = snapshot
            logger.info(
                "统一搜索别名同步完成: aliases=%s source_records=%s",
                len(alias_to_origins),
                source_record_count,
            )
            return SearchAliasSyncResult(
                ok=True,
                alias_count=len(alias_to_origins),
                source_record_count=source_record_count,
                message="同步成功",
            )

    def _download(self) -> bytes:
        request = Request(
            self.source_url,
            headers={"User-Agent": DEFAULT_REMOTE_DOWNLOAD_USER_AGENT},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            final_url = str(response.geturl() or self.source_url)
            _validate_source_url(final_url)
            if final_url != self.source_url:
                raise RuntimeError(
                    f"别名接口不允许重定向: {self.source_url} -> {final_url}"
                )
            content_type = str(
                response.headers.get_content_type()
                or "application/octet-stream"
            ).lower()
            if content_type not in _ALLOWED_CONTENT_TYPES:
                raise RuntimeError(
                    f"别名接口返回了不允许的 Content-Type: {content_type}"
                )
            payload = response.read(self.max_bytes + 1)

        if len(payload) > self.max_bytes:
            raise RuntimeError(
                f"别名接口响应超过大小限制: max_bytes={self.max_bytes}"
            )
        return payload


def _validate_source_url(url: str) -> None:
    """旧接口只为固定官方 HTTP 地址开放，不放宽通用下载策略。"""
    parsed = urlsplit(str(url or "").strip())
    if (
        parsed.scheme != "http"
        or parsed.hostname != _LEGACY_ALIAS_HOST
        or parsed.port != _LEGACY_ALIAS_PORT
        or parsed.path != _LEGACY_ALIAS_PATH
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError(f"不允许的旧版别名接口地址: {url}")


def _parse_alias_payload(
    payload: bytes,
) -> tuple[dict[str, tuple[str, ...]], int]:
    try:
        decoded = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("别名接口返回的 JSON 无效") from exc

    if not isinstance(decoded, dict) or decoded.get("code") != 200:
        raise ValueError("别名接口返回了失败状态")
    rows = decoded.get("data")
    if not isinstance(rows, list):
        raise ValueError("别名接口 data 字段不是数组")
    if len(rows) > SEARCH_ALIAS_MAX_RECORDS:
        raise ValueError(
            f"别名接口记录数超过限制: {len(rows)}"
        )

    aliases: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("is_global", 1) not in (1, True):
            continue
        if row.get("is_active", 1) not in (1, True):
            continue

        origin = _normalize_alias_text(row.get("origin"))
        alias = _normalize_alias_text(row.get("replace"))
        if not origin or not alias or origin == alias:
            continue

        bucket = aliases.setdefault(alias, [])
        if origin not in bucket:
            bucket.append(origin)

    return (
        {alias: tuple(origins) for alias, origins in aliases.items()},
        len(rows),
    )


def _normalize_alias_text(value: object) -> str:
    text = str(value or "").strip()
    if not text or len(text) > SEARCH_ALIAS_MAX_TEXT_LENGTH:
        return ""
    return text
