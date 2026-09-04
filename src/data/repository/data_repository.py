from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.data.repository.bundle.bundle_builder import load_bundle_from_disk
from src.data.repository.bundle.bundle_validation import check_required_files_readable
from src.data.repository.bundle.bundle_validation import GAMEDATA_TABLE_SPECS
from src.data.repository.bundle.bundle_validation import ResourceDataError
from src.data.repository.bundle.bundle_validation import validate_data_bundle
from src.app.config import Config
from src.data.loader._git_gamedata_maintainer import GitGameDataMaintainer
from src.data.models.bundle import DataBundle
from src.data.models._operator_impl import OperatorImpl
from src.domain.models.operator import Operator
from src.domain.models.token import Token
from src.helpers.bundle import build_range, html_tag_format

log = logging.getLogger(__name__)
MAX_RECOVERY_FAILURES_BEFORE_RESTART = 3


class DataNotReadyError(RuntimeError):
    """数据尚未准备好（内存中没有 bundle）"""


@dataclass(frozen=True, slots=True)
class PeriodicRefreshPreparation:
    """子进程中的更新检查与 bundle 构建结果。"""

    ok: bool
    update_result: str
    message: str
    target_version: str | None = None
    bundle: DataBundle | None = None


def prepare_periodic_refresh(
    cfg: Config,
    has_current_bundle: bool,
    current_version: str | None,
    force_rebuild: bool = False,
) -> PeriodicRefreshPreparation:
    """在隔离进程内检查、解包并按需构建新快照。"""
    from src.app.services.resource_update import perform_resource_update

    result = perform_resource_update(
        cfg,
        "recovery" if force_rebuild else "periodic",
        current_bundle_valid=has_current_bundle,
        current_version=current_version,
        force_rebuild=force_rebuild,
    )
    if not result.ok:
        return PeriodicRefreshPreparation(
            ok=False,
            update_result=result.result,
            message=result.message,
            target_version=result.version,
        )

    if result.bundle is None:
        return PeriodicRefreshPreparation(
            ok=True,
            update_result=result.result,
            message=result.message,
            target_version=result.version,
        )

    return PeriodicRefreshPreparation(
        ok=True,
        update_result=result.result,
        message=result.message,
        target_version=result.version,
        bundle=result.bundle,
    )


def configure_periodic_worker() -> None:
    """降低刷新 worker 的 CPU 调度优先级，优先保障 HTTP 主进程。"""
    try:
        os.nice(10)
    except (AttributeError, OSError):
        log.warning("Unable to lower periodic refresh worker priority", exc_info=True)


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
    _periodic_executor: Optional[ProcessPoolExecutor] = field(default=None, init=False, repr=False)
    _resource_files_healthy: bool = field(default=True, init=False, repr=False)
    _validated_bundle_id: int | None = field(default=None, init=False, repr=False)
    _maintenance_failures: int = field(default=0, init=False, repr=False)
    _last_maintenance_error: str | None = field(default=None, init=False, repr=False)
    _restart_pending: bool = field(default=False, init=False, repr=False)
    _updating: bool = field(default=False, init=False, repr=False)
    _recovering: bool = field(default=False, init=False, repr=False)

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
        return self.has_usable_bundle() and self._resource_files_healthy

    def has_usable_bundle(self) -> bool:
        if self._bundle is None:
            return False
        if self._validated_bundle_id == id(self._bundle):
            return True
        try:
            validate_data_bundle(self._bundle)
        except ResourceDataError:
            return False
        self._validated_bundle_id = id(self._bundle)
        return True

    def should_restart(self) -> bool:
        return self._restart_pending and not self.has_usable_bundle()

    def maintenance_state(self) -> dict[str, Any]:
        return {
            "ready": self.is_ready(),
            "bundle_usable": self.has_usable_bundle(),
            "resource_files_healthy": self._resource_files_healthy,
            "updating": self._updating,
            "recovering": self._recovering,
            "recovery_failures": self._maintenance_failures,
            "restart_pending": self._restart_pending,
            "last_error": self._last_maintenance_error,
        }

    def has_local_resources(self) -> bool:
        if self._maintainer is None:
            return False
        return self._maintainer.is_initialized()

    def get_bundle(self) -> DataBundle:
        if not self.has_usable_bundle():
            log.warning("get_bundle: 数据未就绪 (bundle is None)")
            raise DataNotReadyError("Game data bundle is not ready. Call startup_prepare()/ensure_ready() first.")
        bundle = self._bundle
        operators_count = len(bundle.operators) if bundle.operators else 0
        name_index_count = len(bundle.operator_name_to_id) if bundle.operator_name_to_id else 0
        log.debug(
            "get_bundle: operators=%s name_index=%s is_ready=%s",
            operators_count,
            name_index_count,
            True,
        )
        if operators_count == 0:
            log.warning("get_bundle: operators 数量为 0，数据可能未正确加载")
        return bundle

    def get_bundle_version_date(self) -> str | None:
        if self._maintainer is None:
            return None
        release = self._maintainer.current_release()
        return release.version_date or self._maintainer.get_version_date()

    def get_resource_root(self) -> Path:
        if self._bundle is not None:
            root = getattr(self._bundle, "resource_root", None)
            if root is not None:
                return Path(root)
        if self._maintainer is None:
            return self.cfg.ResourcePath
        return self._maintainer.current_resource_root()

    async def startup_prepare(self, force_update_on_first_run: bool = True) -> DataBundle:
        if self._maintainer is None:
            raise RuntimeError("No maintainer configured; cannot perform startup_prepare.")

        if force_update_on_first_run and not self._maintainer.is_initialized():
            from src.app.services.resource_update import perform_resource_update

            log.info("No local gamedata found. Performing first-time git update...")
            result = await asyncio.to_thread(
                perform_resource_update,
                self.cfg,
                "startup",
                current_bundle_valid=False,
                current_version=None,
                force_rebuild=True,
            )
            if not result.ok:
                raise RuntimeError(result.message or "First-time gamedata update failed.")
            if result.bundle is not None:
                self._publish_bundle(result.bundle)
                return result.bundle
            log.info("First-time gamedata update done.")

        return await self.refresh_from_disk()

    async def ensure_ready(self) -> DataBundle:
        if self.has_usable_bundle():
            return self._bundle

        async with self._ready_lock:
            if self.has_usable_bundle():
                return self._bundle

            log.info("Loading game data bundle from disk...")
            bundle = await asyncio.to_thread(self._load_bundle)
            self._publish_bundle(bundle)
            operators_count = len(bundle.operators) if bundle.operators else 0
            name_index_count = len(bundle.operator_name_to_id) if bundle.operator_name_to_id else 0
            log.info(
                "Game data bundle loaded. version=%s operators=%s name_index=%s",
                getattr(bundle, "version", ""),
                operators_count,
                name_index_count,
            )
            if operators_count == 0:
                log.warning("ensure_ready: 加载完成但 operators 数量为 0！请检查游戏数据文件。")
            return bundle

    async def refresh_from_disk(self) -> DataBundle:
        async with self._update_lock:
            log.info("Refreshing game data bundle from disk...")
            try:
                bundle = await asyncio.to_thread(self._load_bundle)
                self._publish_bundle(bundle)
            except Exception as exc:
                self._record_maintenance_failure(exc, count_recovery=False)
                raise
            log.info("Game data bundle refreshed. version=%s", getattr(bundle, "version", ""))
            return bundle

    async def ensure_bundle_fresh_from_disk(self) -> DataBundle | None:
        if self._maintainer is None:
            return self._bundle
        if not self._maintainer.is_initialized():
            return self._bundle

        release = self._maintainer.current_release()
        disk_version = release.version or self._maintainer.get_version(short=True, with_dirty=False)
        if self._bundle is None:
            return await self.refresh_from_disk()

        bundle_version = getattr(self._bundle, "version", None)
        bundle_root = getattr(self._bundle, "resource_root", None)
        if bundle_version != disk_version or bundle_root != release.root:
            return await self.refresh_from_disk()

        if not self.has_usable_bundle():
            return await self.refresh_from_disk()

        healthy, message = check_required_files_readable(
            release.root,
            GAMEDATA_TABLE_SPECS,
        )
        self._resource_files_healthy = healthy
        if not healthy:
            self._last_maintenance_error = message

        return self._bundle

    async def update_and_refresh(self, *, force_rebuild: bool = False) -> bool:
        """Check for resource updates and atomically publish a rebuilt bundle.

        Returns ``True`` only when a new resource version was loaded.  The
        existing bundle remains available to readers while update IO and bundle
        construction run in an isolated worker process.
        """
        if self._maintainer is None:
            log.warning("No maintainer configured; skip update.")
            return False
        if self._restart_pending:
            log.warning("已进入 restart_pending，停止启动新的资源事务")
            return False

        async with self._update_lock:
            self._updating = True
            self._recovering = force_rebuild
            try:
                if force_rebuild:
                    result = await self._prepare_periodic_refresh(force_rebuild=True)
                else:
                    result = await self._prepare_periodic_refresh()
            except Exception as exc:
                self._record_maintenance_failure(
                    exc,
                    resources_unhealthy=force_rebuild or not self.has_usable_bundle(),
                    count_recovery=force_rebuild,
                )
                raise
            finally:
                self._updating = False
                self._recovering = False
            if not result.ok:
                log.warning("Update gamedata on disk failed: %s", result.message)
                if result.update_result != "already_running":
                    self._record_maintenance_failure(
                        RuntimeError(result.message),
                        resources_unhealthy=force_rebuild or not self.has_usable_bundle(),
                        count_recovery=force_rebuild,
                    )
                return False

            if result.bundle is None:
                log.info(
                    "Game data is already up to date; keeping current bundle. version=%s",
                    getattr(self._bundle, "version", None),
                )
                return False

            # Python 对象引用赋值是原子的；只有完整新快照返回主进程后才切换。
            self._publish_bundle(result.bundle)
            log.info(
                "Bundle reloaded after update. version=%s",
                getattr(result.bundle, "version", ""),
            )
            return True

    async def recover_if_needed(self) -> bool:
        if self._restart_pending:
            return False
        try:
            await self.ensure_bundle_fresh_from_disk()
        except Exception as exc:
            log.warning("活动资源检查失败，准备自动恢复: %s", exc)
        if self.is_ready():
            return False
        return await self.update_and_refresh(force_rebuild=True)

    async def close(self) -> None:
        """关闭延迟创建的周期刷新子进程池。"""
        executor = self._periodic_executor
        if executor is None:
            return
        self._periodic_executor = None
        await asyncio.to_thread(
            executor.shutdown,
            wait=True,
            cancel_futures=True,
        )

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
        resource_root = self.cfg.ResourcePath
        version = None
        if self._maintainer is not None:
            release = self._maintainer.current_release()
            resource_root = release.root
            version = release.version or self._maintainer.get_version(short=True, with_dirty=False)
        bundle = load_bundle_from_disk(
            self.cfg,
            version=version,
            resource_root=resource_root,
        )
        validate_data_bundle(bundle)
        return bundle

    async def _prepare_periodic_refresh(
        self,
        *,
        force_rebuild: bool = False,
    ) -> PeriodicRefreshPreparation:
        executor = self._get_periodic_executor()
        bundle = self._bundle
        current_version = getattr(bundle, "version", None)
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                executor,
                prepare_periodic_refresh,
                self.cfg,
                self.has_usable_bundle() and self._resource_files_healthy,
                current_version,
                force_rebuild,
            )
        except BrokenProcessPool:
            # 子进程异常退出后丢弃已损坏的池，下次周期自动重建。
            if self._periodic_executor is executor:
                self._periodic_executor = None
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    def _get_periodic_executor(self) -> ProcessPoolExecutor:
        executor = self._periodic_executor
        if executor is None:
            executor = ProcessPoolExecutor(
                max_workers=1,
                mp_context=multiprocessing.get_context("spawn"),
                initializer=configure_periodic_worker,
                # bundle 很大；每次任务后回收 worker，避免空闲子进程长期占用峰值内存。
                max_tasks_per_child=1,
            )
            self._periodic_executor = executor
        return executor

    def _publish_bundle(self, bundle: DataBundle) -> None:
        validate_data_bundle(bundle)
        resource_root = getattr(bundle, "resource_root", None)
        if resource_root is not None:
            healthy, message = check_required_files_readable(
                Path(resource_root),
                GAMEDATA_TABLE_SPECS,
            )
            if not healthy:
                raise ResourceDataError(message or "活动资源文件不可读")
        # Python 对象引用赋值是原子的；新快照通过全部校验后才对请求可见。
        self._bundle = bundle
        self._validated_bundle_id = id(bundle)
        self._resource_files_healthy = True
        self._maintenance_failures = 0
        self._last_maintenance_error = None
        self._restart_pending = False

    def _record_maintenance_failure(
        self,
        exc: Exception,
        *,
        resources_unhealthy: bool = True,
        count_recovery: bool = False,
    ) -> None:
        self._last_maintenance_error = str(exc) or exc.__class__.__name__
        if resources_unhealthy:
            self._resource_files_healthy = False
        if self.has_usable_bundle() or not count_recovery:
            return
        self._maintenance_failures += 1
        if self._maintenance_failures >= MAX_RECOVERY_FAILURES_BEFORE_RESTART:
            self._restart_pending = True
