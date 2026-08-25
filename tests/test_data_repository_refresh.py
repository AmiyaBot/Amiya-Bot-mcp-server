from __future__ import annotations

import asyncio
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace

from src.app.config import Config
from src.app.services.resource_update import ResourceUpdateExecutionResult
from src.data.loader._git_gamedata_maintainer import GitGameDataMaintainer
from src.data.repository.data_repository import (
    DataRepository,
    PeriodicRefreshPreparation,
    prepare_periodic_refresh,
)


def _repository(tmp_path: Path) -> DataRepository:
    return DataRepository(
        cfg=Config(
            ProjectRoot=tmp_path,
            ResourcePath=tmp_path / "resources",
            GameDataRepo="https://example.test/gamedata.git",
        )
    )


def _bundle(version: str):
    return SimpleNamespace(
        version=version,
        operators={"operator": object()},
        operator_name_to_id={"Operator": "operator"},
    )


def test_update_check_keeps_current_bundle_when_resources_are_up_to_date(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    current_bundle = _bundle("abc1234")
    repository._bundle = current_bundle

    async def fake_prepare(_repository):
        assert repository.get_bundle() is current_bundle
        return PeriodicRefreshPreparation(
            ok=True,
            update_result="up_to_date",
            message="already current",
            target_version="abc1234",
        )

    monkeypatch.setattr(DataRepository, "_prepare_periodic_refresh", fake_prepare)

    changed = asyncio.run(repository.update_and_refresh())

    assert changed is False
    assert repository.get_bundle() is current_bundle


def test_update_check_atomically_replaces_bundle_when_resources_changed(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    current_bundle = _bundle("abc1234")
    rebuilt_bundle = _bundle("def5678")
    repository._bundle = current_bundle

    async def fake_prepare(_repository):
        assert repository.get_bundle() is current_bundle
        return PeriodicRefreshPreparation(
            ok=True,
            update_result="updated",
            message="updated",
            target_version="def5678",
            bundle=rebuilt_bundle,
        )

    monkeypatch.setattr(DataRepository, "_prepare_periodic_refresh", fake_prepare)

    changed = asyncio.run(repository.update_and_refresh())

    assert changed is True
    assert repository.get_bundle() is rebuilt_bundle


def test_stale_bundle_is_rebuilt_even_when_disk_is_already_current(tmp_path, monkeypatch):
    rebuilt_bundle = _bundle("def5678")

    def fake_update(_cfg, _trigger):
        return ResourceUpdateExecutionResult(
            ok=True,
            result="up_to_date",
            message="already current",
            version="def5678",
        )

    load_calls = []

    def fake_load(cfg, version):
        load_calls.append((cfg, version))
        return rebuilt_bundle

    monkeypatch.setattr(
        "src.app.services.resource_update.perform_resource_update",
        fake_update,
    )
    monkeypatch.setattr(
        "src.data.repository.data_repository.load_bundle_from_disk",
        fake_load,
    )

    result = prepare_periodic_refresh(
        _repository(tmp_path).cfg,
        has_current_bundle=True,
        current_version="abc1234",
    )

    assert result.bundle is rebuilt_bundle
    assert load_calls[0][1] == "def5678"


def test_periodic_executor_runs_work_in_a_separate_process(tmp_path):
    repository = _repository(tmp_path)

    async def run():
        loop = asyncio.get_running_loop()
        worker_pid = await loop.run_in_executor(
            repository._get_periodic_executor(),
            os.getpid,
        )
        await repository.close()
        return worker_pid

    worker_pid = asyncio.run(run())

    assert worker_pid != os.getpid()


def test_extract_zip_publishes_only_a_complete_validated_directory(tmp_path):
    maintainer = GitGameDataMaintainer("https://example.test/repo.git", tmp_path)
    maintainer.assets_dir.mkdir()
    (maintainer.gamedata_dir / "excel").mkdir(parents=True)
    old_marker = maintainer.gamedata_dir / "excel" / "character_table.json"
    old_marker.write_text('{"version": "old"}', encoding="utf-8")
    (maintainer.gamedata_dir / "removed_in_new_version.json").write_text(
        "old",
        encoding="utf-8",
    )
    with zipfile.ZipFile(maintainer.assets_dir / "gamedata.zip", "w") as archive:
        archive.writestr("excel/character_table.json", '{"version": "new"}')
        archive.writestr("excel/item_table.json", "{}")

    assert maintainer.extract_zip() is True

    assert old_marker.read_text(encoding="utf-8") == '{"version": "new"}'
    assert not (maintainer.gamedata_dir / "removed_in_new_version.json").exists()
    assert not list(tmp_path.glob(".gamedata-staging-*"))


def test_invalid_extraction_keeps_previous_gamedata(tmp_path):
    maintainer = GitGameDataMaintainer("https://example.test/repo.git", tmp_path)
    maintainer.assets_dir.mkdir()
    (maintainer.gamedata_dir / "excel").mkdir(parents=True)
    old_marker = maintainer.gamedata_dir / "excel" / "character_table.json"
    old_marker.write_text('{"version": "old"}', encoding="utf-8")
    with zipfile.ZipFile(maintainer.assets_dir / "gamedata.zip", "w") as archive:
        archive.writestr("excel/item_table.json", "{}")

    assert maintainer.extract_zip() is False

    assert old_marker.read_text(encoding="utf-8") == '{"version": "old"}'
    assert not list(tmp_path.glob(".gamedata-staging-*"))
