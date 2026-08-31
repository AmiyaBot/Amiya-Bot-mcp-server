# src/app/bootstrap.py
from pathlib import Path
import logging

from src.app.renderers.jinja_html_renderer import JinjaHtmlRenderer
from src.app.context import AppContext
from src.app.config import load_from_disk
from src.app.card_service import CardService
from src.app.cache_permissions import repair_cache_file_permissions
from src.data.repository.data_repository import DataRepository

logger = logging.getLogger(__name__)

async def build_context_from_disk(cfg) -> AppContext:

    cache_root = cfg.ResourcePath / "cache"
    repaired = 0
    failed = 0
    for path in (
        cache_root / "cards",
        cache_root / "char_skin",
        cache_root / "integrated_strategy_collectible_icons",
    ):
        path_repaired, path_failed = repair_cache_file_permissions(path)
        repaired += path_repaired
        failed += path_failed
    logger.info(
        "缓存文件权限检查完成: repaired=%s failed=%s",
        repaired,
        failed,
    )

    data_repo = DataRepository(
        cfg=cfg,
    )
    await data_repo.startup_prepare(False)

    card_service = CardService(cfg)

    ctx = AppContext(
        cfg=cfg,
        data_repository=data_repo,
        card_service=card_service
    )

    return ctx
