from __future__ import annotations

from src.app.config import load_from_disk
from src.app.services.resource_update import perform_resource_update


def main() -> int:
    cfg = load_from_disk()
    result = perform_resource_update(cfg, "manual")
    return 0 if result.ok or result.result == "already_running" else 1


if __name__ == "__main__":
    raise SystemExit(main())