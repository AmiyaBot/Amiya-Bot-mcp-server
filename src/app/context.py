# src/app/context.py
from dataclasses import dataclass

from src.app.config import Config
from src.data.repository.data_repository import DataRepository
from src.app.card_service import CardService
from src.app.remote_download_manager import RemoteDownloadManager
from src.app.services.search_card_cache import SearchCardCache


@dataclass(slots=True)
class AppContext:
    cfg: Config
    data_repository: DataRepository
    card_service: CardService
    prefer_local_artifact_path: bool = False
    output_format: str = "markdown"
    download_manager: RemoteDownloadManager | None = None
    search_card_cache: SearchCardCache | None = None

    def __post_init__(self) -> None:
        if self.download_manager is None:
            self.download_manager = RemoteDownloadManager(
                max_concurrency=self.cfg.RemoteAssetDownloadConcurrency,
            )
        if self.search_card_cache is None:
            self.search_card_cache = SearchCardCache(self.cfg)
