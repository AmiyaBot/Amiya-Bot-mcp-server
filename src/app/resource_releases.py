from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.app.config import Config
from src.app.runtime_state import runtime_state_dir
from src.data.repository.bundle.bundle_validation import check_required_files_readable
from src.data.repository.bundle.bundle_validation import GAMEDATA_TABLE_SPECS


ACTIVE_RELEASE_SCHEMA_VERSION = 1
ACTIVE_RELEASE_FILE_NAME = "active-resource-release.json"
INACTIVE_RELEASE_MIN_AGE_SECONDS = 24 * 60 * 60
log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResourceRelease:
    release_id: str
    root: Path
    version: str | None
    version_date: str | None
    created_at: str | None
    managed: bool = True
    self_contained: bool = True


def releases_dir(cfg: Config) -> Path:
    return cfg.ResourcePath / "releases"


def resource_update_transactions_dir(cfg: Config) -> Path:
    return runtime_state_dir(cfg) / "resource-updates"


def active_release_path(cfg: Config) -> Path:
    return runtime_state_dir(cfg) / ACTIVE_RELEASE_FILE_NAME


def legacy_release(cfg: Config) -> ResourceRelease:
    return ResourceRelease(
        release_id="legacy",
        root=cfg.ResourcePath,
        version=None,
        version_date=None,
        created_at=None,
        managed=False,
        self_contained=False,
    )


def read_active_release(cfg: Config) -> ResourceRelease:
    """读取原子发布清单；当前版本损坏时回退到清单中的上一版本。"""
    payload = _read_manifest(active_release_path(cfg))
    for key in ("current", "previous"):
        release = _release_from_payload(cfg, payload.get(key))
        if release is not None and _has_release_marker(release.root):
            return release
    return legacy_release(cfg)


def read_published_releases(
    cfg: Config,
) -> tuple[ResourceRelease | None, ResourceRelease | None]:
    payload = _read_manifest(active_release_path(cfg))
    return (
        _release_from_payload(cfg, payload.get("current")),
        _release_from_payload(cfg, payload.get("previous")),
    )


def publish_active_release(cfg: Config, release: ResourceRelease) -> None:
    """用同目录 os.replace 原子切换清单，并保留上一版本用于回退。"""
    current, previous = read_published_releases(cfg)
    fallback = next(
        (
            item
            for item in (current, previous)
            if item is not None
            and item.release_id != release.release_id
            and _has_release_marker(item.root)
        ),
        None,
    )
    payload = {
        "schema_version": ACTIVE_RELEASE_SCHEMA_VERSION,
        "current": _release_payload(cfg, release),
        "previous": _release_payload(cfg, fallback) if fallback is not None else None,
        "published_at": _now_iso(),
    }

    path = active_release_path(cfg)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def prune_inactive_releases(
    cfg: Config,
    *,
    min_age_seconds: int = INACTIVE_RELEASE_MIN_AGE_SECONDS,
) -> None:
    """仅回收带有效元数据且超过保护期的非活动版本。"""
    current, previous = read_published_releases(cfg)
    protected = {
        item.release_id
        for item in (current, previous)
        if item is not None
    }
    root = releases_dir(cfg)
    if not root.is_dir():
        return

    cutoff = time.time() - max(0, min_age_seconds)
    try:
        candidates = list(root.iterdir())
    except OSError:
        log.warning("无法枚举资源版本目录: %s", root, exc_info=True)
        return
    for candidate in candidates:
        if candidate.name in protected or candidate.is_symlink() or not candidate.is_dir():
            continue
        metadata_path = candidate / "release.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            valid_metadata = (
                isinstance(metadata, dict)
                and metadata.get("release_id") == candidate.name
            )
            old_enough = metadata_path.stat().st_mtime <= cutoff
        except (OSError, json.JSONDecodeError):
            continue
        if not valid_metadata or not old_enough:
            continue
        try:
            shutil.rmtree(candidate)
        except OSError:
            log.warning("回收旧资源版本失败: %s", candidate, exc_info=True)


def _read_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if payload.get("schema_version") != ACTIVE_RELEASE_SCHEMA_VERSION:
        return {}
    return payload


def _release_from_payload(cfg: Config, raw: object) -> ResourceRelease | None:
    if not isinstance(raw, dict):
        return None
    release_id = str(raw.get("release_id") or "").strip()
    relative_path = str(raw.get("relative_path") or "").strip()
    if not release_id or not relative_path:
        return None

    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    root = cfg.ResourcePath / relative
    if root.parent != releases_dir(cfg) or root.name != release_id:
        return None
    return ResourceRelease(
        release_id=release_id,
        root=root,
        version=_optional_str(raw.get("version")),
        version_date=_optional_str(raw.get("version_date")),
        created_at=_optional_str(raw.get("created_at")),
        self_contained=bool(raw.get("self_contained", True)),
    )


def _release_payload(cfg: Config, release: ResourceRelease) -> dict:
    if not release.managed:
        raise ValueError("Legacy resources cannot be published as a managed release")
    if release.root.parent != releases_dir(cfg) or release.root.name != release.release_id:
        raise ValueError(f"Release path is outside managed releases: {release.root}")
    payload = asdict(release)
    payload.pop("root", None)
    payload.pop("managed", None)
    payload["relative_path"] = str(release.root.relative_to(cfg.ResourcePath))
    return payload


def _has_release_marker(root: Path) -> bool:
    healthy, _ = check_required_files_readable(root, GAMEDATA_TABLE_SPECS)
    return healthy


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
