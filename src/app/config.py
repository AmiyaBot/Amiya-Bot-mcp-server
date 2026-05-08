import json
import os
from pathlib import Path

from dataclasses import dataclass
from typing import Optional

FILE_PATH = Path(__file__).parent.parent.parent.resolve()
GLOBAL_CONFIG_DIR_NAME = "amiyabot-cli"
GLOBAL_CONFIG_FILE_NAME = "config.json"
CONFIG_FIELDS = (
    "ResourcePath",
    "GameDataRepo",
    "BaseUrl",
    "CommandServiceUrl",
    "McpDnsRebindingProtectionEnabled",
)

@dataclass
class Config:
    ProjectRoot: Path
    ResourcePath: Path
    GameDataRepo: Optional[str] = None
    BaseUrl: Optional[str] = None
    CommandServiceUrl: Optional[str] = None
    McpDnsRebindingProtectionEnabled: bool = False


@dataclass(frozen=True)
class ConfigLayer:
    path: Path
    payload: dict


@dataclass(frozen=True)
class ConfigState:
    config: Config
    active_path: Path
    layer_paths: tuple[Path, ...]
    key_sources: dict[str, Path]


def _resolve_global_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "").strip()
    config_home = Path(xdg_config_home).expanduser() if xdg_config_home else Path.home() / ".config"
    return config_home / GLOBAL_CONFIG_DIR_NAME / GLOBAL_CONFIG_FILE_NAME


def resolve_global_config_path() -> Path:
    return _resolve_global_config_path()


def _candidate_config_paths() -> list[Path]:
    global_config_path = _resolve_global_config_path()
    _ensure_global_config_exists(global_config_path)
    return [
        FILE_PATH / "data" / "config.json",
        global_config_path,
        FILE_PATH / "resources" / "config.json",
        FILE_PATH / "config.json",
    ]


def _ensure_global_config_exists(path: Path) -> None:
    if path.exists():
        return

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    except OSError:
        pass


def _load_json_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, dict) else {}


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "y"}:
            return True
        if normalized in {"0", "false", "no", "off", "n", ""}:
            return False
    return default


def inspect_config_state() -> ConfigState:

    project_root = FILE_PATH
    resource_path = None

    layers: list[ConfigLayer] = []
    merged_config: dict = {}
    key_sources: dict[str, Path] = {}
    active_path: Path | None = None

    for path in _candidate_config_paths():
        if not path.exists():
            continue

        payload = _load_json_config(path)
        layers.append(ConfigLayer(path=path, payload=payload))
        merged_config.update(payload)

        contributed = False
        for key in CONFIG_FIELDS:
            if key in payload:
                key_sources[key] = path
                contributed = True

        if contributed:
            active_path = path

    if not layers:
        raise FileNotFoundError("Could not find config.json in expected locations.")

    cfg_resource_path = str(merged_config.get("ResourcePath", "")).strip()
    if cfg_resource_path == "":
        resource_path = Path((FILE_PATH / "resources").resolve())
    else:
        resource_path = Path(cfg_resource_path).expanduser()

    if resource_path is None:
        raise FileNotFoundError("Could not find config.json in expected locations.")

    config = Config(
        ProjectRoot=project_root,
        ResourcePath=resource_path,
        GameDataRepo=merged_config.get("GameDataRepo", None),
        BaseUrl=merged_config.get("BaseUrl", None),
        CommandServiceUrl=merged_config.get("CommandServiceUrl", None),
        McpDnsRebindingProtectionEnabled=_coerce_bool(
            merged_config.get("McpDnsRebindingProtectionEnabled", False),
            default=False,
        ),
    )

    return ConfigState(
        config=config,
        active_path=active_path or layers[-1].path,
        layer_paths=tuple(layer.path for layer in layers),
        key_sources=key_sources,
    )


def resolve_effective_config_path() -> Path:
    return inspect_config_state().active_path


def resolve_merged_config_paths() -> tuple[Path, ...]:
    return inspect_config_state().layer_paths


def load_from_disk() -> Config:
    return inspect_config_state().config


