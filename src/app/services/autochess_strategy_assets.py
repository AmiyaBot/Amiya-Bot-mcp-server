from pathlib import Path


def strategy_portrait_path(project_root, entry):
    return Path(project_root) / 'data/templates/autochess_strategy/assets' / f"{entry['source_id']}.png"
