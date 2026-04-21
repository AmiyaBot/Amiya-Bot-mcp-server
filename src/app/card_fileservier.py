# src/app/card_fileserver.py
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.app.config import Config
from src.helpers.card_urls import CHAR_SKIN_MOUNT_PATH, DEFAULT_MOUNT_PATH


def _mount_static_dir(app: FastAPI, *, mount_path: str, root: Path, name: str) -> None:
  root.mkdir(parents=True, exist_ok=True)
  app.mount(
    mount_path,
    StaticFiles(directory=str(root), html=False),
    name=name,
  )


def register_cardserver_asgi(app: FastAPI, *, cfg: Config) -> None:
    """
    访问规则：
      GET {mount_path}/{template}/{payload_key}/artifact.png
      GET {mount_path}/{template}/{payload_key}/artifact.html
      ...
    """
    card_cache_root: Path = cfg.ResourcePath / "cache" / "cards"
    skin_cache_root: Path = cfg.ResourcePath / "cache" / "char_skin"

    _mount_static_dir(app, mount_path=DEFAULT_MOUNT_PATH, root=card_cache_root, name="cards")
    _mount_static_dir(app, mount_path=CHAR_SKIN_MOUNT_PATH, root=skin_cache_root, name="char-skins")
