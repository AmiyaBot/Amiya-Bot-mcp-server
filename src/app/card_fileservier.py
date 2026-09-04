# src/app/card_fileserver.py
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.app.config import Config
from src.app.resource_releases import read_active_release
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


class ActiveGameAssets:
    """按请求绑定当前内存 Bundle 的资源目录，避免静态挂载固化旧版本。"""

    def __init__(self, app: FastAPI, cfg: Config):
        self.app = app
        self.cfg = cfg

    async def __call__(self, scope, receive, send) -> None:
        ctx = getattr(self.app.state, "ctx", None)
        repository = getattr(ctx, "data_repository", None)
        if repository is not None:
            resource_root = repository.get_resource_root()
        else:
            resource_root = read_active_release(self.cfg).root
        static_app = StaticFiles(
            directory=str(Path(resource_root) / "assets"),
            html=False,
            check_dir=False,
        )
        await static_app(scope, receive, send)


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
    # AI-REMOVED 2026-09-04:
    # Reason: 固定目录会让 StaticFiles 永久绑定旧资源，无法跟随原子发布切换。
    # Trigger: 版本化资源目录与原子清单切换需求。
    # Evidence: StaticFiles 在注册时固定 directory，运行期不会读取活动发布清单。
    # Replacement: ActiveGameAssets.__call__ 按当前 Bundle 解析 assets 根目录。
    # Risk: Low
    # Human Review: Required
    #
    # Original code:
    # game_assets_root: Path = cfg.ResourcePath / "assets"

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
    app.mount(
        GAME_ASSETS_MOUNT_PATH,
        ActiveGameAssets(app, cfg),
        name="game-assets",
    )
    # AI-REMOVED 2026-09-04:
    # Reason: 固定 StaticFiles 挂载不能与内存 Bundle 同步切换资源版本。
    # Trigger: 资源发布必须覆盖 assets、gamedata 与 Bundle 的同一版本边界。
    # Evidence: _mount_static_dir 的 root 仅在应用启动时求值。
    # Replacement: 上方 ActiveGameAssets 动态 ASGI 挂载。
    # Risk: Low
    # Human Review: Required
    #
    # Original code:
    # _mount_static_dir(
    #     app,
    #     mount_path=GAME_ASSETS_MOUNT_PATH,
    #     root=game_assets_root,
    #     name="game-assets",
    # )
