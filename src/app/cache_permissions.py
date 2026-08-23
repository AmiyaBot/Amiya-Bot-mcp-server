from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_FILE_MODE = 0o644


def repair_cache_file_permissions(cache_root: Path) -> tuple[int, int]:
    """Normalize existing cache files so the application can serve them.

    Returns ``(repaired, failed)`` for startup diagnostics. Symlinks are skipped
    so a cache scan never changes permissions outside the cache tree.
    """
    repaired = 0
    failed = 0

    if not cache_root.exists():
        return repaired, failed

    try:
        candidates = cache_root.rglob("*")
        for path in candidates:
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                path.chmod(CACHE_FILE_MODE)
                repaired += 1
            except OSError:
                failed += 1
                logger.exception("修复缓存文件权限失败: %s", path)
    except OSError:
        failed += 1
        logger.exception("扫描缓存目录失败: %s", cache_root)

    return repaired, failed
