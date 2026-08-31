from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Lock
import time
from types import SimpleNamespace

import pytest

from src.app import remote_download_manager
from src.app.remote_download_manager import (
    RemoteDownloadManager,
    RemoteDownloadRequest,
    RemoteDownloadResult,
    get_context_download_manager,
)
from src.app.services import operator_skin_assets


def test_download_many_shares_one_concurrency_limit(monkeypatch):
    manager = RemoteDownloadManager(max_concurrency=2)
    state_lock = Lock()
    active = 0
    peak = 0

    def fake_download(request: RemoteDownloadRequest) -> RemoteDownloadResult:
        nonlocal active, peak
        with state_lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with state_lock:
            active -= 1
        return RemoteDownloadResult(
            payload=request.url.encode(),
            content_type="application/octet-stream",
            final_url=request.url,
        )

    monkeypatch.setattr(manager, "_download_sync", fake_download)
    requests = [
        RemoteDownloadRequest(url=f"https://assets.example.test/{index}.png")
        for index in range(8)
    ]

    results = asyncio.run(manager.download_many(requests))

    assert len(results) == 8
    assert peak == 2


def test_download_encodes_path_and_validates_response(monkeypatch):
    captured = {}

    class FakeHeaders:
        @staticmethod
        def get_content_type():
            return "image/png"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def read(size):
            captured["read_size"] = size
            return b"png"

        @staticmethod
        def geturl():
            return "https://media.prts.wiki/path/%E7%9A%AE%E8%82%A4.png"

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["user_agent"] = request.get_header("User-agent")
        return FakeResponse()

    monkeypatch.setattr(remote_download_manager, "urlopen", fake_urlopen)
    manager = RemoteDownloadManager(max_concurrency=1)

    result = asyncio.run(
        manager.download(
            RemoteDownloadRequest(
                url="https://media.prts.wiki/path/皮肤.png",
                timeout_seconds=12,
                max_bytes=8,
                allowed_hosts=frozenset({"media.prts.wiki"}),
                allowed_content_types=frozenset({"image/png"}),
            )
        )
    )

    assert captured["url"].endswith("/path/%E7%9A%AE%E8%82%A4.png")
    assert captured["timeout"] == 12
    assert captured["read_size"] == 9
    assert captured["user_agent"].startswith("AmiyaBotMCPServer/")
    assert result.payload == b"png"
    assert result.content_type == "image/png"


@pytest.mark.parametrize(
    "url",
    [
        "http://media.prts.wiki/a.png",
        "https://user:secret@media.prts.wiki/a.png",
        "https://example.test/a.png",
    ],
)
def test_download_rejects_unsafe_or_unlisted_sources(url):
    manager = RemoteDownloadManager(max_concurrency=1)

    with pytest.raises(ValueError):
        asyncio.run(
            manager.download(
                RemoteDownloadRequest(
                    url=url,
                    allowed_hosts=frozenset({"media.prts.wiki"}),
                )
            )
        )


def test_context_reuses_one_download_manager():
    context = SimpleNamespace(
        cfg=SimpleNamespace(RemoteAssetDownloadConcurrency=4)
    )

    first = get_context_download_manager(context)
    second = get_context_download_manager(context)

    assert first is second
    assert first.max_concurrency == 4


def test_operator_skin_download_uses_shared_manager(tmp_path: Path, monkeypatch):
    manager = RemoteDownloadManager(max_concurrency=2)
    submitted = []

    def fake_download(request: RemoteDownloadRequest) -> RemoteDownloadResult:
        submitted.append(request)
        return RemoteDownloadResult(
            payload=b"skin-image",
            content_type="image/webp",
            final_url=request.url,
        )

    monkeypatch.setattr(manager, "_download_sync", fake_download)
    operator_skin_assets._download_locks.clear()
    context = SimpleNamespace(
        cfg=SimpleNamespace(
            ResourcePath=tmp_path,
            BaseUrl="https://example.test/",
        ),
        download_manager=manager,
    )

    artifact = asyncio.run(
        operator_skin_assets._resolve_and_download(
            context,
            "char_test#1",
            "https://media.prts.wiki/file/测试皮肤.png",
        )
    )

    assert artifact.path == tmp_path / "cache/char_skin/char_test#1.webp"
    assert artifact.path.read_bytes() == b"skin-image"
    assert len(submitted) == 1
    assert submitted[0].allowed_hosts == frozenset({"media.prts.wiki"})
    assert submitted[0].max_bytes == 50 * 1024 * 1024
