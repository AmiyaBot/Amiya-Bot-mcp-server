from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.data.repository.bundle.bundle_builder import load_bundle_from_disk
from src.app.config import Config
from src.data.loader._git_gamedata_maintainer import GitGameDataMaintainer
from src.data.models.bundle import DataBundle
from src.data.models._operator_impl import OperatorImpl
from src.domain.models.operator import Operator
from src.domain.models.token import Token
from src.helpers.bundle import build_range, html_tag_format

log = logging.getLogger(__name__)


class DataNotReadyError(RuntimeError):
    """数据尚未准备好（内存中没有 bundle）"""

@dataclass(slots=True)
class DataRepository:
    """
    DataRepository：持有当前 DataBundle（只读快照）并提供刷新能力。

    - get_bundle() 不做 IO
    - startup_prepare()/refresh_from_disk()/ensure_ready() 才做 IO
    """

    cfg: Config

    _maintainer: Optional[GitGameDataMaintainer] = field(default=None, init=False, repr=False)
    _bundle: Optional[DataBundle] = field(default=None, init=False, repr=False)

    _ready_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _update_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self):
        # 约定：cfg.ResourcePath 指向resources, 解包数据根目录（里面有 excel/character_table.json 等）
        if self.cfg.ResourcePath is None:
            raise ValueError("ResourcePath must be configured")
        if self.cfg.GameDataRepo is None:
            raise ValueError("GameDataRepo must be configured")
        
        data_root = self.cfg.ResourcePath
        self._maintainer = GitGameDataMaintainer(self.cfg.GameDataRepo, data_root)

    # ---------- public ----------

    def is_ready(self) -> bool:
        return self._bundle is not None

    def get_bundle(self) -> DataBundle:
        if self._bundle is None:
            raise DataNotReadyError("Game data bundle is not ready. Call startup_prepare()/ensure_ready() first.")
        return self._bundle

    async def startup_prepare(self, force_update_on_first_run: bool = True) -> DataBundle:
        if self._maintainer is None:
            raise RuntimeError("No maintainer configured; cannot perform startup_prepare.")

        if force_update_on_first_run and not self._maintainer.is_initialized():
            log.info("No local gamedata found. Performing first-time git update...")
            ok = await asyncio.to_thread(self._maintainer.update)
            if not ok:
                raise RuntimeError("First-time gamedata update failed.")
            log.info("First-time gamedata update done.")

        return await self.refresh_from_disk()

    async def ensure_ready(self) -> DataBundle:
        if self._bundle is not None:
            return self._bundle

        async with self._ready_lock:
            if self._bundle is not None:
                return self._bundle

            log.info("Loading game data bundle from disk...")
            bundle = await asyncio.to_thread(self._load_bundle)
            self._bundle = bundle
            log.info("Game data bundle loaded. version=%s", getattr(bundle, "version", ""))
            return bundle

    async def refresh_from_disk(self) -> DataBundle:
        async with self._update_lock:
            log.info("Refreshing game data bundle from disk...")
            bundle = await asyncio.to_thread(self._load_bundle)
            self._bundle = bundle
            log.info("Game data bundle refreshed. version=%s", getattr(bundle, "version", ""))
            return bundle

    async def update_and_refresh(self) -> bool:
        if self._maintainer is None:
            log.warning("No maintainer configured; skip update.")
            return False

        async with self._update_lock:
            log.info("Updating gamedata on disk (git+zip)...")
            ok = await asyncio.to_thread(self._maintainer.update)
            if not ok:
                log.warning("Update gamedata on disk failed.")
                return False

            log.info("Update ok. Reloading bundle into memory...")
            bundle = await asyncio.to_thread(self._load_bundle)
            self._bundle = bundle
            log.info("Bundle reloaded after update. version=%s", getattr(bundle, "version", ""))
            return True

    # ---------- internal ----------

    def _read_json(self, name: str, folder: str) -> Dict[str, Any]:
        """
        直接读取文件：<ResourcePath>/<folder>/<name>.json
        读不到/解析失败则返回 {}
        """
        path = Path(folder) / f"{name}.json"
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            log.exception("Failed to read json: %s", path)
            return {}

    def _load_bundle(self) -> DataBundle:
        version = None
        if self._maintainer is not None:
            version = self._maintainer.get_version(short=True, with_dirty=True)
        return load_bundle_from_disk(self.cfg, version=version)
