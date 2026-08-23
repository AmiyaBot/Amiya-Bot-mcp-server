from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path

from src.app.cache_permissions import CACHE_FILE_MODE, repair_cache_file_permissions
from src.app.card_service import CardService
from src.app.services import operator_skin_assets


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_find_cached_skin_path_repairs_unreadable_cache(tmp_path: Path) -> None:
    cached = tmp_path / "char_2012_typhon#1.webp"
    cached.write_bytes(b"skin")
    cached.chmod(0o000)

    found = operator_skin_assets._find_cached_skin_path(
        tmp_path,
        "char_2012_typhon#1",
    )

    assert found == cached
    assert cached.read_bytes() == b"skin"
    assert _mode(cached) == CACHE_FILE_MODE


def test_find_cached_skin_path_removes_empty_cache(tmp_path: Path) -> None:
    cached = tmp_path / "char_2012_typhon#1.webp"
    cached.touch()

    found = operator_skin_assets._find_cached_skin_path(
        tmp_path,
        "char_2012_typhon#1",
    )

    assert found is None
    assert not cached.exists()


def test_skin_cache_write_sets_mode_before_and_after_replace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    temp_path = tmp_path / ".char_2012_typhon#1.download"
    target_path = tmp_path / "char_2012_typhon#1.webp"
    real_replace = os.replace
    mode_at_replace: list[int] = []

    def replace_and_reset_mode(source: Path, target: Path) -> None:
        mode_at_replace.append(_mode(Path(source)))
        real_replace(source, target)
        Path(target).chmod(0o000)

    monkeypatch.setattr(operator_skin_assets.os, "replace", replace_and_reset_mode)

    operator_skin_assets._write_cache_file(temp_path, target_path, b"payload")

    assert mode_at_replace == [CACHE_FILE_MODE]
    assert target_path.read_bytes() == b"payload"
    assert _mode(target_path) == CACHE_FILE_MODE
    assert not temp_path.exists()


def test_card_atomic_writes_set_mode_before_and_after_replace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = object.__new__(CardService)
    real_replace = os.replace
    modes_at_replace: list[int] = []

    def replace_and_reset_mode(source: Path, target: Path) -> None:
        modes_at_replace.append(_mode(Path(source)))
        real_replace(source, target)
        Path(target).chmod(0o000)

    monkeypatch.setattr("src.app.card_service.os.replace", replace_and_reset_mode)

    text_path = tmp_path / "artifact.html"
    bytes_path = tmp_path / "artifact.png"
    asyncio.run(service._atomic_write_text(text_path, "content"))
    asyncio.run(service._atomic_write_bytes(bytes_path, b"image"))

    assert modes_at_replace == [CACHE_FILE_MODE, CACHE_FILE_MODE]
    assert text_path.read_text() == "content"
    assert bytes_path.read_bytes() == b"image"
    assert _mode(text_path) == CACHE_FILE_MODE
    assert _mode(bytes_path) == CACHE_FILE_MODE


def test_repair_cache_file_permissions_recursively(tmp_path: Path) -> None:
    first = tmp_path / "char_skin" / "skin.webp"
    second = tmp_path / "cards" / "operator" / "artifact.png"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_bytes(b"skin")
    second.write_bytes(b"card")
    first.chmod(0o000)
    second.chmod(0o600)

    repaired, failed = repair_cache_file_permissions(tmp_path)

    assert (repaired, failed) == (2, 0)
    assert _mode(first) == CACHE_FILE_MODE
    assert _mode(second) == CACHE_FILE_MODE
