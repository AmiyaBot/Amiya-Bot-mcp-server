from __future__ import annotations

import asyncio
import fcntl
import os
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.app.config import Config
from src.app.context import get_bundle_resource_root
from src.app.resource_releases import ResourceRelease
from src.app.resource_releases import active_release_path
from src.app.resource_releases import publish_active_release
from src.app.resource_releases import prune_inactive_releases
from src.app.resource_releases import read_active_release
from src.app.services.resource_update import perform_resource_update
from src.app.services.resource_update import resource_update_in_progress
from src.app.runtime_state import resource_update_lock_path
from src.data.loader._git_gamedata_maintainer import GitGameDataMaintainer
from src.data.loader._git_gamedata_maintainer import PreparedResourceRelease
from src.data.repository.data_repository import DataRepository
from src.data.repository.data_repository import PeriodicRefreshPreparation
from src.data.repository.bundle.bundle_validation import GAMEDATA_TABLE_SPECS
from src.data.repository.bundle.bundle_builder import load_bundle_from_disk
from src.data.repository.bundle.bundle_validation import ResourceDataError


def _config(tmp_path: Path, repo: str = "https://example.test/assets.git") -> Config:
    return Config(
        ProjectRoot=tmp_path,
        ResourcePath=tmp_path / "resources",
        GameDataRepo=repo,
    )


def _release(cfg: Config, release_id: str, version: str) -> ResourceRelease:
    root = cfg.ResourcePath / "releases" / release_id
    for name, folder in GAMEDATA_TABLE_SPECS:
        table = root / "gamedata" / folder / f"{name}.json"
        table.parent.mkdir(parents=True, exist_ok=True)
        table.write_text('{"fixture": {}}', encoding="utf-8")
    return ResourceRelease(
        release_id=release_id,
        root=root,
        version=version,
        version_date="2026-09-04",
        created_at="2026-09-04T00:00:00+00:00",
    )


def _write_required_zip(archive: zipfile.ZipFile) -> None:
    for name, folder in GAMEDATA_TABLE_SPECS:
        archive.writestr(f"{folder}/{name}.json", '{"fixture": {}}')


def test_active_release_manifest_keeps_readable_previous_release(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    first = _release(cfg, "first", "abc1234")
    second = _release(cfg, "second", "def5678")

    publish_active_release(cfg, first)
    publish_active_release(cfg, second)

    assert read_active_release(cfg) == second
    assert not list(active_release_path(cfg).parent.glob(".active-resource-release.json.*.tmp"))

    marker = second.root / "gamedata" / "excel" / "character_table.json"
    marker.chmod(0)
    assert read_active_release(cfg) == first


def test_missing_required_table_fails_instead_of_publishing_an_empty_bundle(
    tmp_path: Path,
) -> None:
    cfg = _config(tmp_path)

    with pytest.raises(ResourceDataError, match="character_table.json"):
        load_bundle_from_disk(cfg, version="broken")


def test_release_cleanup_protects_current_and_previous(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    maintainer = GitGameDataMaintainer(cfg.GameDataRepo or "", cfg.ResourcePath)
    first = _release(cfg, "first", "one")
    second = _release(cfg, "second", "two")
    third = _release(cfg, "third", "three")
    for release in (first, second, third):
        maintainer._write_release_metadata(release)
        os.utime(release.root / "release.json", (0, 0))
        publish_active_release(cfg, release)

    prune_inactive_releases(cfg, min_age_seconds=0)

    assert first.root.exists() is False
    assert second.root.is_dir()
    assert third.root.is_dir()


def test_prepare_and_publish_release_never_mutates_legacy_paths(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with zipfile.ZipFile(source / "gamedata.zip", "w") as archive:
        _write_required_zip(archive)
    (source / "avatar").mkdir()
    (source / "avatar" / "operator.png").write_bytes(b"png")
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Resource Test",
            "-c",
            "user.email=resource@example.test",
            "commit",
            "-m",
            "fixture",
        ],
        cwd=source,
        check=True,
        capture_output=True,
    )

    cfg = _config(tmp_path, str(source))
    legacy_marker = cfg.ResourcePath / "gamedata" / "legacy.txt"
    legacy_marker.parent.mkdir(parents=True)
    legacy_marker.write_text("keep", encoding="utf-8")
    maintainer = GitGameDataMaintainer(str(source), cfg.ResourcePath)

    prepared = maintainer.prepare_release()

    assert prepared.needs_publish is True
    assert legacy_marker.read_text(encoding="utf-8") == "keep"
    assert (prepared.root / "gamedata" / "excel" / "character_table.json").is_file()
    assert oct((prepared.root / "gamedata" / "excel" / "character_table.json").stat().st_mode & 0o777) == "0o644"

    published = maintainer.publish_prepared_release(prepared)

    assert read_active_release(cfg) == published
    assert published.root.parent == cfg.ResourcePath / "releases"
    assert legacy_marker.read_text(encoding="utf-8") == "keep"


def test_invalid_candidate_bundle_is_never_published(tmp_path: Path, monkeypatch) -> None:
    cfg = _config(tmp_path)
    transaction = cfg.ResourcePath / "runtime" / "resource-updates" / "test"
    candidate = transaction / "release"
    candidate.mkdir(parents=True)
    prepared = PreparedResourceRelease(
        release_id="invalid",
        root=candidate,
        transaction_dir=transaction,
        version="invalid",
        version_date=None,
        result="updated",
        message="prepared",
    )
    published = False

    monkeypatch.setattr(
        GitGameDataMaintainer,
        "prepare_release",
        lambda self, force_rebuild=False: prepared,
    )

    def fake_publish(self, item):
        nonlocal published
        published = True
        raise AssertionError("invalid candidate must not publish")

    monkeypatch.setattr(GitGameDataMaintainer, "publish_prepared_release", fake_publish)
    monkeypatch.setattr(
        "src.app.services.resource_update.load_bundle_from_disk",
        lambda *args, **kwargs: SimpleNamespace(
            version="invalid",
            resource_root=candidate,
            operators={},
            operator_name_to_id={},
        ),
    )

    result = perform_resource_update(cfg, "test")

    assert result.ok is False
    assert published is False
    assert not active_release_path(cfg).exists()


def test_local_archive_recovery_removes_a_partial_clone(tmp_path: Path, monkeypatch) -> None:
    cfg = _config(tmp_path)
    assets = cfg.ResourcePath / "assets"
    assets.mkdir(parents=True)
    with zipfile.ZipFile(assets / "gamedata.zip", "w") as archive:
        _write_required_zip(archive)
    maintainer = GitGameDataMaintainer(cfg.GameDataRepo or "", cfg.ResourcePath)
    monkeypatch.setattr(maintainer, "_remote_head_hash", lambda: "a" * 40)

    def fail_after_partial_clone(args, cwd=None):
        destination = Path(args[-1])
        destination.mkdir(parents=True)
        (destination / "partial").write_text("partial", encoding="utf-8")
        return 1

    monkeypatch.setattr(maintainer, "_run_git", fail_after_partial_clone)

    prepared = maintainer.prepare_release(force_rebuild=True)
    published = maintainer.publish_prepared_release(prepared)

    assert published.root.joinpath("assets").is_symlink()
    assert published.root.joinpath("assets/gamedata.zip").is_file()


def test_liveness_restart_is_latched_only_after_recovery_is_exhausted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = DataRepository(cfg=_config(tmp_path))

    async def fail_recovery(_repository, *, force_rebuild=False):
        assert force_rebuild is True
        return PeriodicRefreshPreparation(
            ok=False,
            update_result="failed",
            message="still broken",
        )

    monkeypatch.setattr(DataRepository, "_prepare_periodic_refresh", fail_recovery)

    assert asyncio.run(repository.update_and_refresh(force_rebuild=True)) is False
    assert repository.should_restart() is False
    assert asyncio.run(repository.update_and_refresh(force_rebuild=True)) is False
    assert repository.should_restart() is False
    assert asyncio.run(repository.update_and_refresh(force_rebuild=True)) is False
    assert repository.should_restart() is True


def test_valid_in_memory_bundle_is_never_sacrificed_to_a_restart(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = DataRepository(cfg=_config(tmp_path))
    repository._bundle = SimpleNamespace(
        version="last-known-good",
        operators={"operator": object()},
        operator_name_to_id={"Operator": "operator"},
    )
    repository._resource_files_healthy = False

    async def fail_recovery(_repository, *, force_rebuild=False):
        return PeriodicRefreshPreparation(
            ok=False,
            update_result="failed",
            message="storage unavailable",
        )

    monkeypatch.setattr(DataRepository, "_prepare_periodic_refresh", fail_recovery)

    for _ in range(5):
        assert asyncio.run(repository.update_and_refresh(force_rebuild=True)) is False

    assert repository.is_ready() is False
    assert repository.has_usable_bundle() is True
    assert repository.should_restart() is False


def test_resource_update_lock_is_authoritative(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    lock_path = resource_update_lock_path(cfg)
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert resource_update_in_progress(cfg) is True
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    assert resource_update_in_progress(cfg) is False


def test_request_keeps_the_resource_root_bound_to_its_bundle(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    bundle = SimpleNamespace(resource_root=old_root)
    context = SimpleNamespace(
        cfg=SimpleNamespace(ResourcePath=new_root),
        data_repository=SimpleNamespace(get_resource_root=lambda: new_root),
    )

    assert get_bundle_resource_root(bundle, context) == old_root
