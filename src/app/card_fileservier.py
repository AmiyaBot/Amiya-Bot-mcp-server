# src/app/card_fileserver.py
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.app.card_service import CardService
from src.app.config import Config


def register_cardserver_asgi(app: FastAPI, *, cfg: Config) -> None:
    """
    访问规则：
      GET {mount_path}/{template}/{payload_key}/artifact.png
      GET {mount_path}/{template}/{payload_key}/artifact.html
      ...
    """
    mount_path = "/cards"

    cache_root: Path = cfg.ResourcePath / "cache" / "cards"
    cache_root.mkdir(parents=True, exist_ok=True)

    app.mount(
        mount_path,
        StaticFiles(directory=str(cache_root), html=False),
        name="cards",
    )
