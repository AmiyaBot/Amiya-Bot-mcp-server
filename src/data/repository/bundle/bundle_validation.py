from __future__ import annotations

from pathlib import Path
from typing import Any

from src.data.models.bundle import DataBundle


GAMEDATA_TABLE_SPECS: tuple[tuple[str, str], ...] = (
    ("character_table", "excel"),
    ("uniequip_table", "excel"),
    ("battle_equip_table", "excel"),
    ("favor_table", "excel"),
    ("handbook_team_table", "excel"),
    ("handbook_info_table", "excel"),
    ("item_table", "excel"),
    ("stage_table", "excel"),
    ("zone_table", "excel"),
    ("enemy_handbook_table", "excel"),
    ("enemy_database", "levels/enemydata"),
    ("range_table", "excel"),
    ("skill_table", "excel"),
    ("gacha_table", "excel"),
    ("skin_table", "excel"),
    ("building_data", "excel"),
    ("charword_table", "excel"),
    ("char_meta_table", "excel"),
    ("roguelike_topic_table", "excel"),
)


class ResourceDataError(RuntimeError):
    """磁盘资源或由其构建的 Bundle 不满足服务运行条件。"""


def validate_data_bundle(bundle: DataBundle | Any) -> None:
    operators = getattr(bundle, "operators", None) or {}
    name_index = getattr(bundle, "operator_name_to_id", None) or {}
    if not operators:
        raise ResourceDataError("Bundle 校验失败: operators 为空")
    if not name_index:
        raise ResourceDataError("Bundle 校验失败: operator_name_to_id 为空")

    dangling_ids = {
        operator_id
        for operator_id in name_index.values()
        if operator_id not in operators
    }
    if dangling_ids:
        sample = ", ".join(sorted(str(item) for item in dangling_ids)[:5])
        raise ResourceDataError(f"Bundle 校验失败: 干员名称索引存在悬空 ID: {sample}")


def check_required_files_readable(
    resource_root: Path,
    table_specs: tuple[tuple[str, str], ...],
) -> tuple[bool, str | None]:
    """只读取必需文件的首字节，供高频健康检查发现权限和挂载故障。"""
    game_root = resource_root / "gamedata"
    for name, folder in table_specs:
        path = game_root / folder / f"{name}.json"
        try:
            with path.open("rb") as file:
                if not file.read(1):
                    return False, f"必需资源文件为空: {path}"
        except OSError as exc:
            return False, f"必需资源文件不可读: {path}: {exc}"
    return True, None
