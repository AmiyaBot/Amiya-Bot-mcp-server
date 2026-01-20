# src/helper/card_urls.py
from __future__ import annotations

from urllib.parse import quote

from fastapi import Request

from src.app.config import Config


DEFAULT_MOUNT_PATH = "/cards"


def build_card_url(
    *,
    cfg: Config,
    template: str,
    payload_key: str,
    format: str,
    mount_path: str = DEFAULT_MOUNT_PATH,
) -> str:
    """
    用于非 HTTP 场景（bot / 离线任务）
    依赖 cfg 中的 BaseUrl
    """
    base = getattr(cfg, "BaseUrl", None)
    if not base:
        raise RuntimeError("Config.BaseUrl is required to build card URL")

    payload_key_url = quote(payload_key, safe="")

    return (
        base.rstrip("/")
        + f"{mount_path}/{template}/{payload_key_url}/artifact.{format}"
    )


def build_card_url_from_request(
    request: Request,
    *,
    template: str,
    payload_key: str,
    format: str,
    mount_path: str = DEFAULT_MOUNT_PATH,
) -> str:
    """
    用于 FastAPI endpoint
    自动从 request.base_url 推导 host/scheme
    """
    payload_key_url = quote(payload_key, safe="")

    return (
        str(request.base_url).rstrip("/")
        + f"{mount_path}/{template}/{payload_key_url}/artifact.{format}"
    )
