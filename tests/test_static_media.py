from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

from starlette.responses import FileResponse

from src.app.static_media import (
    IMMUTABLE_CACHE_CONTROL,
    REVALIDATE_CACHE_CONTROL,
    StaticCacheControlMiddleware,
    StaticCachePolicy,
    install_static_mime_types,
)


def _headers_of(messages: list[dict]) -> dict[bytes, bytes]:
    start = next(m for m in messages if m["type"] == "http.response.start")
    return dict(start["headers"])


def _call_middleware(
    middleware: StaticCacheControlMiddleware,
    *,
    scope_path: str,
) -> list[dict]:
    sent: list[dict] = []

    async def receiver() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def sender(message: dict) -> None:
        sent.append(message)

    scope = {"type": "http", "path": scope_path, "method": "GET", "headers": []}
    asyncio.run(middleware(scope, receiver, sender))
    return sent


def _status_app(status: int, headers: list[tuple[bytes, bytes]] | None = None):
    async def app(scope, receive, send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": headers or [],
            }
        )
        await send({"type": "http.response.body", "body": b"payload"})

    return app


def test_install_static_mime_types_registers_webp() -> None:
    install_static_mime_types()

    assert mimetypes.guess_type("char_1035_wisdel#1.webp")[0] == "image/webp"


def test_file_response_uses_image_webp_for_webp_suffix(tmp_path: Path) -> None:
    install_static_mime_types()
    skin = tmp_path / "char_1035_wisdel#1.webp"
    skin.write_bytes(b"RIFF....WEBP")

    response = FileResponse(skin)

    assert response.media_type == "image/webp"


def test_card_mount_gets_immutable_cache_control() -> None:
    middleware = StaticCacheControlMiddleware(
        _status_app(200, [(b"content-type", b"image/png")])
    )

    messages = _call_middleware(
        middleware,
        scope_path="/cards/operator_info/operator:char_1:ade7aa2:card-v21/artifact.png",
    )

    assert _headers_of(messages)[b"cache-control"] == IMMUTABLE_CACHE_CONTROL.encode()


def test_char_skin_mount_gets_immutable_cache_control() -> None:
    middleware = StaticCacheControlMiddleware(_status_app(200))

    messages = _call_middleware(middleware, scope_path="/char-skins/char_002_amiya#1.webp")

    assert _headers_of(messages)[b"cache-control"] == IMMUTABLE_CACHE_CONTROL.encode()


def test_game_assets_mount_revalidates_instead_of_immutable() -> None:
    middleware = StaticCacheControlMiddleware(_status_app(200))

    messages = _call_middleware(middleware, scope_path="/game-assets/chararts/a.png")

    assert _headers_of(messages)[b"cache-control"] == REVALIDATE_CACHE_CONTROL.encode()


def test_error_responses_are_not_cached() -> None:
    middleware = StaticCacheControlMiddleware(_status_app(404))

    messages = _call_middleware(middleware, scope_path="/cards/missing/artifact.png")

    assert b"cache-control" not in _headers_of(messages)


def test_unrelated_paths_keep_their_headers() -> None:
    middleware = StaticCacheControlMiddleware(_status_app(200))

    messages = _call_middleware(middleware, scope_path="/mcp")

    assert b"cache-control" not in _headers_of(messages)


def test_existing_cache_control_is_preserved() -> None:
    middleware = StaticCacheControlMiddleware(
        _status_app(200, [(b"cache-control", b"private, max-age=0")])
    )

    messages = _call_middleware(middleware, scope_path="/cards/a/b/artifact.png")

    assert _headers_of(messages)[b"cache-control"] == b"private, max-age=0"


def test_custom_policies_override_defaults() -> None:
    middleware = StaticCacheControlMiddleware(
        _status_app(200),
        policies=[StaticCachePolicy("/cards", "no-store")],
    )

    messages = _call_middleware(middleware, scope_path="/cards/a/b/artifact.png")

    assert _headers_of(messages)[b"cache-control"] == b"no-store"
