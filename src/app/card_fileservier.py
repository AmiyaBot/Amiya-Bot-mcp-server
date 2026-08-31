# src/app/card_fileserver.py
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.app.config import Config
from src.helpers.card_urls import (
    CHAR_SKIN_MOUNT_PATH,
    DEFAULT_MOUNT_PATH,
    GAME_ASSETS_MOUNT_PATH,
    INTEGRATED_STRATEGY_COLLECTIBLE_ICON_MOUNT_PATH,
)


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
    collectible_icon_cache_root: Path = (
        cfg.ResourcePath / "cache" / "integrated_strategy_collectible_icons"
    )
    game_assets_root: Path = cfg.ResourcePath / "assets"

    _mount_static_dir(
        app,
        mount_path=DEFAULT_MOUNT_PATH,
        root=card_cache_root,
        name="cards",
    )
    _mount_static_dir(
        app,
        mount_path=CHAR_SKIN_MOUNT_PATH,
        root=skin_cache_root,
        name="char-skins",
    )
    _mount_static_dir(
        app,
        mount_path=INTEGRATED_STRATEGY_COLLECTIBLE_ICON_MOUNT_PATH,
        root=collectible_icon_cache_root,
        name="integrated-strategy-collectible-icons",
    )
    _mount_static_dir(
        app,
        mount_path=GAME_ASSETS_MOUNT_PATH,
        root=game_assets_root,
        name="game-assets",
    )
