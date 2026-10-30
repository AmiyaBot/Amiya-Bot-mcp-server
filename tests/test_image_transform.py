from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from PIL import Image

from src.app import image_transform
from src.app.image_transform import (
    DEFAULT_QUALITY,
    TransformableStaticFiles,
    parse_transform_params,
)


def _scope(path: str, query: bytes = b"", method: str = "GET") -> dict:
    return {
        "type": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "method": method,
        "headers": [],
        "root_path": "",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
    }


async def _collect(app, scope: dict) -> list[dict]:
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def _body(sent: list[dict]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def _start(sent: list[dict]) -> dict:
    return next(m for m in sent if m["type"] == "http.response.start")


def _write_png(path: Path, size: tuple[int, int] = (1600, 900)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (20, 120, 220)).save(path, format="PNG")


@pytest.fixture()
def mount(tmp_path: Path) -> TransformableStaticFiles:
    root = tmp_path / "cards"
    _write_png(root / "a" / "artifact.png")
    return TransformableStaticFiles(
        directory=str(root),
        cache_directory=tmp_path / "thumbs",
        html=False,
    )


def test_parse_width_and_quality() -> None:
    assert parse_transform_params(b"w=1080&q=85") == (1080, 85)


def test_parse_without_width_is_noop() -> None:
    assert parse_transform_params(b"") is None
    assert parse_transform_params(b"q=80") is None


def test_parse_invalid_width_is_noop() -> None:
    assert parse_transform_params(b"w=abc") is None


def test_parse_clamps_out_of_range_values() -> None:
    assert parse_transform_params(b"w=99999&q=0") == (2048, 1)
    assert parse_transform_params(b"w=1") == (16, DEFAULT_QUALITY)


def test_quality_defaults_when_omitted() -> None:
    assert parse_transform_params(b"w=800") == (800, DEFAULT_QUALITY)


def test_no_query_serves_original(mount: TransformableStaticFiles) -> None:
    sent = asyncio.run(_collect(mount, _scope("/a/artifact.png")))

    start = _start(sent)
    assert start["status"] == 200
    assert dict(start["headers"])[b"content-type"] == b"image/png"


def test_width_query_returns_downscaled_webp(mount: TransformableStaticFiles) -> None:
    sent = asyncio.run(_collect(mount, _scope("/a/artifact.png", b"w=400")))

    start = _start(sent)
    assert start["status"] == 200
    headers = dict(start["headers"])
    assert headers[b"content-type"] == b"image/webp"

    with Image.open(io.BytesIO(_body(sent))) as image:
        assert image.format == "WEBP"
        assert image.width == 400
        assert image.height == 225


def test_width_query_reuses_cached_transformation(mount: TransformableStaticFiles) -> None:
    first = asyncio.run(_collect(mount, _scope("/a/artifact.png", b"w=400")))
    second = asyncio.run(_collect(mount, _scope("/a/artifact.png", b"w=400")))

    assert _body(first) == _body(second)
    assert len(list(mount.cache_directory.glob("*.webp"))) == 1


def test_width_query_never_upscales(mount: TransformableStaticFiles) -> None:
    sent = asyncio.run(_collect(mount, _scope("/a/artifact.png", b"w=2048")))

    with Image.open(io.BytesIO(_body(sent))) as image:
        assert image.width == 1600


def test_missing_file_still_returns_404(mount: TransformableStaticFiles) -> None:
    with pytest.raises(Exception) as excinfo:
        asyncio.run(_collect(mount, _scope("/a/missing.png", b"w=400")))

    assert getattr(excinfo.value, "status_code", None) == 404


def test_post_is_rejected(mount: TransformableStaticFiles) -> None:
    with pytest.raises(Exception) as excinfo:
        asyncio.run(_collect(mount, _scope("/a/artifact.png", b"w=400", method="POST")))

    assert getattr(excinfo.value, "status_code", None) == 405


def test_missing_pillow_falls_back_to_original(
    mount: TransformableStaticFiles,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(image_transform, "_PILImage", None)

    sent = asyncio.run(_collect(mount, _scope("/a/artifact.png", b"w=400")))

    start = _start(sent)
    assert start["status"] == 200
    assert dict(start["headers"])[b"content-type"] == b"image/png"


def test_missing_pillow_warning_is_emitted_once(
    mount: TransformableStaticFiles,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(image_transform, "_PILImage", None)
    monkeypatch.setattr(image_transform, "_pillow_warning_emitted", False)

    with caplog.at_level("ERROR", logger=image_transform.__name__):
        asyncio.run(_collect(mount, _scope("/a/artifact.png", b"w=400")))
        asyncio.run(_collect(mount, _scope("/a/artifact.png", b"w=400")))
        asyncio.run(_collect(mount, _scope("/a/artifact.png", b"w=400")))

    assert len([r for r in caplog.records if "Pillow" in r.message]) == 1
