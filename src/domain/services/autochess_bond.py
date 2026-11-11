"""当期常规盟约资料，与角色卡共享当期判定。"""
from datetime import datetime, timezone


def current_autochess_version(bundle, *, now=None):
    table = ((getattr(bundle, "tables", {}) or {}).get("gamedata") or {}).get("activity_table") or {}
    versions = (table.get("autoChessData") or {}).get("versionInfoDict") or {}
    timestamp = (now or datetime.now(timezone.utc)).timestamp()
    active = [v for v in versions.values()
              if v.get("startTime", 0) <= timestamp < v.get("endTime", 0)
              and not v.get("isOffseason")]
    return max(active, key=lambda v: (v.get("startTime", 0), v.get("versionId", ""))) if active else None


def current_bonds(bundle, *, now=None):
    version = current_autochess_version(bundle, now=now)
    if not version:
        return {}
    return {key: entry for key, entry in (getattr(bundle, "autochess_entries", {}) or {}).items()
            if entry.get("kind") == "bond" and entry.get("ruleset") == "standard"
            and entry.get("activity_id") == version.get("activityId")
            and entry.get("version_id") == version.get("versionId")}


def bond_search_item(entry):
    return {"id": entry["id"], "name": entry["name"], "type": "卫戍协议盟约",
            "activity_name": entry["activity_name"].replace(":", "：")}


def bond_detail(bundle, entry):
    members = {}
    for member_id in entry.get("member_ids", []):
        chess = bundle.autochess_entries[member_id]
        members[chess["operator_id"]] = {"干员ID": chess["operator_id"], "名称": chess["name"], "等阶": chess["tier"]}
    count = entry.get("activation_count")
    condition = entry.get("activation_condition")
    scope = {"BOARD": "在场", "BOARD_AND_DECK": "在场及整备区"}.get(condition)
    activation = f"{scope} {count} 名不同的【{entry['name']}】干员" if scope and count else ""
    return {"ID": entry["id"], "卫戍协议": entry["activity_name"].replace(":", "："),
            "名称": entry["name"], "激活条件": activation, "效果": entry["description"],
            "所属棋子": sorted(members.values(), key=lambda m: (m["等阶"], m["名称"]))}
