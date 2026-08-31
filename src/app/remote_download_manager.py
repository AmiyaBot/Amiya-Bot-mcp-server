from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from email.message import Message
from threading import BoundedSemaphore
from typing import Iterable, Mapping
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen


DEFAULT_REMOTE_DOWNLOAD_CONCURRENCY = 3
DEFAULT_REMOTE_DOWNLOAD_TIMEOUT_SECONDS = 30.0
DEFAULT_REMOTE_DOWNLOAD_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_REMOTE_DOWNLOAD_USER_AGENT = (
    "AmiyaBotMCPServer/1.0 "
    "(+https://github.com/AmiyaBot/Amiya-Bot-mcp-server)"
)


@dataclass(frozen=True)
class RemoteDownloadRequest:
    """一次受控 HTTP 下载请求。

    调用方负责定义允许的主机、内容类型、超时和最大响应体；下载管理器统一
    负责 URL 编码、并发限制及非阻塞调度。
    """

    url: str
    timeout_seconds: float = DEFAULT_REMOTE_DOWNLOAD_TIMEOUT_SECONDS
    max_bytes: int = DEFAULT_REMOTE_DOWNLOAD_MAX_BYTES
    headers: Mapping[str, str] = field(default_factory=dict)
    allowed_hosts: frozenset[str] | None = None
    allowed_content_types: frozenset[str] | None = None


@dataclass(frozen=True)
class RemoteDownloadResult:
    payload: bytes
    content_type: str
    final_url: str


class RemoteDownloadManager:
    """供任意应用任务复用的进程内远程下载并发控制器。

    使用线程信号量而不是 asyncio.Semaphore，使同一个管理器即使被 CLI、测试
    或 Web 服务的不同事件循环调用，也共享同一个并发上限。
    """

    def __init__(self, max_concurrency: int = DEFAULT_REMOTE_DOWNLOAD_CONCURRENCY):
        try:
            normalized_concurrency = int(max_concurrency)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_concurrency 必须是正整数") from exc
        if normalized_concurrency <= 0:
            raise ValueError("max_concurrency 必须是正整数")

        self.max_concurrency = normalized_concurrency
        self._slots = BoundedSemaphore(normalized_concurrency)

    async def download(self, request: RemoteDownloadRequest) -> RemoteDownloadResult:
        """提交一个下载请求；等待共享并发槽时不会阻塞事件循环。"""
        _validate_request(request)
        return await asyncio.to_thread(self._download_with_slot, request)

    async def download_many(
        self,
        requests: Iterable[RemoteDownloadRequest],
    ) -> list[RemoteDownloadResult]:
        """批量提交下载请求，实际并发仍受管理器的全局上限约束。"""
        return list(await asyncio.gather(*(self.download(item) for item in requests)))

    def _download_with_slot(
        self,
        request: RemoteDownloadRequest,
    ) -> RemoteDownloadResult:
        with self._slots:
            return self._download_sync(request)

    def _download_sync(self, request: RemoteDownloadRequest) -> RemoteDownloadResult:
        encoded_url = _encode_url_path(request.url)
        headers = {
            "User-Agent": DEFAULT_REMOTE_DOWNLOAD_USER_AGENT,
            **dict(request.headers),
        }
        http_request = Request(encoded_url, headers=headers)
        with urlopen(http_request, timeout=request.timeout_seconds) as response:
            final_url = str(response.geturl() or encoded_url)
            _validate_url(final_url, allowed_hosts=request.allowed_hosts)
            content_type = _content_type(response.headers)
            payload = response.read(request.max_bytes + 1)

        if len(payload) > request.max_bytes:
            raise RuntimeError(
                f"远程下载超过大小限制: max_bytes={request.max_bytes} url={request.url}"
            )
        if (
            request.allowed_content_types is not None
            and content_type not in request.allowed_content_types
        ):
            raise RuntimeError(
                f"远程下载返回了不允许的 Content-Type: {content_type}"
            )

        return RemoteDownloadResult(
            payload=payload,
            content_type=content_type,
            final_url=final_url,
        )


def get_context_download_manager(context) -> RemoteDownloadManager:
    """获取上下文共享下载器；兼容测试和旧调用方的轻量上下文对象。"""
    manager = getattr(context, "download_manager", None)
    if isinstance(manager, RemoteDownloadManager):
        return manager

    cfg = getattr(context, "cfg", None)
    concurrency = getattr(
        cfg,
        "RemoteAssetDownloadConcurrency",
        DEFAULT_REMOTE_DOWNLOAD_CONCURRENCY,
    )
    manager = RemoteDownloadManager(max_concurrency=concurrency)
    try:
        context.download_manager = manager
    except (AttributeError, TypeError):
        pass
    return manager


def _validate_request(request: RemoteDownloadRequest) -> None:
    _validate_url(request.url, allowed_hosts=request.allowed_hosts)
    if request.timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必须大于 0")
    if request.max_bytes <= 0:
        raise ValueError("max_bytes 必须大于 0")


def _validate_url(url: str, *, allowed_hosts: frozenset[str] | None) -> None:
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("远程下载仅允许无用户凭据的 HTTPS URL")
    if allowed_hosts is not None and parsed.hostname.lower() not in {
        host.lower() for host in allowed_hosts
    }:
        raise ValueError(f"远程下载主机不在允许列表中: {parsed.hostname}")


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


def _content_type(headers: Message) -> str:
    return str(headers.get_content_type() or "application/octet-stream").lower()
