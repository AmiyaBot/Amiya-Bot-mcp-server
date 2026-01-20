# src/app/context.py
from dataclasses import dataclass
from typing import Optional

from src.app.config import Config
from src.data.repository.data_repository import DataRepository
from src.app.card_service import CardService

@dataclass(slots=True)
class AppContext:
    cfg: Config
    data_repository: DataRepository
    card_service: CardService
