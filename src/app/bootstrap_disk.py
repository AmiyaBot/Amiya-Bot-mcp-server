# src/app/bootstrap.py
from pathlib import Path
import logging

from src.app.renderers.jinja_html_renderer import JinjaHtmlRenderer
from src.app.context import AppContext
from src.app.config import load_from_disk
from src.app.card_service import CardService
from src.data.repository.data_repository import DataRepository

logger = logging.getLogger(__name__)

async def build_context_from_disk(cfg) -> AppContext:

    data_repo = DataRepository(
        cfg=cfg,
    )
    await data_repo.startup_prepare(True)

    card_service = CardService(cfg)

    ctx = AppContext(
        cfg=cfg,
        data_repository=data_repo,
        card_service=card_service
    )

    return ctx