from __future__ import annotations

from pathlib import Path

from src.app.config import Config


def runtime_state_dir(cfg: Config) -> Path:
    path = cfg.ResourcePath / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_update_status_path(cfg: Config) -> Path:
    return runtime_state_dir(cfg) / "resource-update-status.json"


def resource_update_lock_path(cfg: Config) -> Path:
    return runtime_state_dir(cfg) / "resource-update.lock"


def resource_update_log_path(cfg: Config) -> Path:
    return runtime_state_dir(cfg) / "resource-update.log"


def command_service_log_path(cfg: Config) -> Path:
    return runtime_state_dir(cfg) / "command-service.log"