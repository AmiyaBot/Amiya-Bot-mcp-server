"""卫戍协议资料索引：保留说明文字，不执行或反推效果参数。"""
from __future__ import annotations

import re
from typing import Any

from src.helpers.bundle import get_table


def clean_autochess_text(value: Any) -> str:
    # 中文尖括号是条件说明，不能使用删除所有 XML 标签的通用清理器。
    text = re.sub(r"<[@$][^>]*>|</>|</?color(?:=[^>]*)?>", "", str(value or ""))
    return text.replace("\\n", "\n").strip()


def build_autochess_entries(tables: dict) -> tuple[dict, dict]:
    table = get_table(tables, "activity_table", default={}) or {}
    characters = get_table(tables, "character_table", default={}) or {}
    entries: dict[str, dict] = {}
    aliases: dict[str, list[str]] = {}
    global_data = table.get("autoChessData") or {}
    for activity_id, versions in (table.get("activity", {}).get("AUTOCHESS") or {}).items():
        for version_id, data in versions.items():
            version = (global_data.get("versionInfoDict") or {}).get(version_id) or {}
            activity = (table.get("basicInfo") or {}).get(activity_id) or {}
            for ruleset, config in [("standard", data), ("training", data.get("trainingData") or {})]:
                if not config:
                    continue
                metadata = {
                    "activity_id": activity_id,
                    "activity_name": clean_autochess_text(activity.get("name") or activity_id),
                    "version_id": version_id,
                    "season_name": clean_autochess_text(version.get("seasonName")),
                    "ruleset": ruleset,
                    "ruleset_name": "教程" if ruleset == "training" else "常规",
                }
                prefix = f"autochess:{activity_id}:{version_id}:{ruleset}"
                training_id = (data.get("trainingData", {}).get("trainingConstData") or {}).get("trainingModeId")
                modes = [
                    {"id": mid, "name": clean_autochess_text(mode.get("name") or mid),
                     "active_bond_ids": list(mode.get("activeBondIdList") or []),
                     "inactive_bond_ids": list(mode.get("inactiveBondIdList") or [])}
                    for mid, mode in (data.get("modeDataDict") or {}).items()
                    if (mid == training_id) == (ruleset == "training")
                ]
                if ruleset == "training":
                    training_const = config.get("trainingConstData") or {}
                    for mode in modes:
                        mode["active_bond_ids"] = training_const.get("trBondIds", mode["active_bond_ids"])
                        mode["inactive_bond_ids"] = training_const.get("trBannedBondIds", mode["inactive_bond_ids"])

                def add(kind: str, source_id: str, name: str, extra: dict, names=()):
                    entry_id = f"{prefix}:{kind}:{source_id}"
                    entry = {"id": entry_id, "source_id": source_id, "kind": kind,
                             "type": {"bond": "卫戍协议盟约", "chess": "卫戍协议棋子", "strategy": "卫戍协议策略"}[kind],
                             "name": name, **metadata, "modes": modes, **extra}
                    entries[entry_id] = entry
                    for alias in dict.fromkeys([name, entry_id, source_id, f"卫戍协议{name}", f"{metadata['activity_name']} {name}", *names]):
                        if alias:
                            aliases.setdefault(alias, []).append(entry_id)

                bonds = config.get("bondInfoDict") or {}
                for bid, bond in bonds.items():
                    add("bond", bid, clean_autochess_text(bond.get("name") or bid), {
                        "description": clean_autochess_text(bond.get("desc")),
                        "activation_count": bond.get("activeCount"),
                        "activation_condition": bond.get("activeCondition"),
                        "member_ids": [f"{prefix}:chess:{cid}" for cid, shop in (config.get("charShopChessDatas") or {}).items()
                                       if bid in ((config.get("charChessDataDict") or {}).get(cid, {}).get("bondIds") or [])],
                    })
                for cid, shop in (config.get("charShopChessDatas") or {}).items():
                    operator_id = shop.get("charId")
                    if shop.get("chessType") == "DIY" or not operator_id or operator_id not in characters:
                        continue
                    variants = []
                    for variant_id in dict.fromkeys([cid, shop.get("goldenChessId")]):
                        chess = (config.get("charChessDataDict") or {}).get(variant_id)
                        if not chess:
                            continue
                        prices = (config.get("shopCharChessInfoData", data.get("shopCharChessInfoData")) or {}).get(str(shop.get("chessLevel"))) or []
                        price = next((p for p in prices if p.get("isGolden") == chess.get("isGolden")), {})
                        traits = []
                        for gid in chess.get("garrisonIds") or []:
                            garrison = (config.get("garrisonDataDict") or {}).get(gid) or {}
                            traits.append({"id": gid, "description": clean_autochess_text(garrison.get("garrisonDesc") or garrison.get("description")),
                                           "trigger": garrison.get("eventType"), "category": clean_autochess_text(garrison.get("eventTypeDesc"))})
                        variants.append({
                            "id": variant_id, "name": "精锐" if chess.get("isGolden") else "普通",
                            "purchase_price": price.get("purchasePrice"), "sale_price": price.get("chessSoldPrice"),
                            "equipment_slots": chess.get("equipSlotNum"),
                            "description": clean_autochess_text(chess.get("desc")),
                            "bonds": [{"id": f"{prefix}:bond:{bid}", "source_id": bid,
                                       "name": clean_autochess_text(bonds.get(bid, {}).get("name") or bid)} for bid in chess.get("bondIds") or []],
                            "traits": traits,
                        })
                    if variants:
                        add("chess", cid, clean_autochess_text(characters[operator_id].get("name") or operator_id),
                            {"operator_id": operator_id, "tier": shop.get("chessLevel"), "variants": variants},
                            [operator_id, shop.get("goldenChessId")])
                band_names = dict(global_data.get("bandDataDict") or {})
                band_names.update((config.get("overrideAutoChessData") or {}).get("bandDataDict") or {})
                for bid, band in (config.get("bandDataListDict") or {}).items():
                    effect = (config.get("effectInfoDataDict") or {}).get(band.get("effectId")) or {}
                    description = clean_autochess_text(band.get("bandDesc"))
                    title = re.match(r"【([^】]+)】", description)
                    name = clean_autochess_text(effect.get("effectName") or (title.group(1) if title else bid))
                    skills = [{"id": sid, "type": skill.get("skillType"),
                               "type_name": {"ACTIVE": "主动", "PASSIVE": "被动", "NONE": "无"}.get(skill.get("skillType"), skill.get("skillType")),
                               "description": clean_autochess_text(skill.get("skillDesc")),
                               "cost": skill.get("skillCost"), "usage_type": skill.get("skillAvailType"),
                               "usage_count": skill.get("skillAvailCount"), "target_type": skill.get("targetType")}
                              for sid, skill in (config.get("skillInfoDataDict") or {}).items()
                              if skill.get("bandId") == bid or sid == band.get("effectId")]
                    band_info = band_names.get(bid) or {}
                    add("strategy", bid, name, {
                        "description": description, "owner_name": clean_autochess_text(band_info.get("bandName")),
                        "unlock_description": clean_autochess_text(band_info.get("unlockDesc")),
                        "initial_hp": band.get("totalHp"), "skills": skills,
                        "inactive_mode_ids": list(band.get("inactiveModeIdList") or []),
                    }, [clean_autochess_text(band_info.get("bandName"))])
    # 排除未收录的自定义棋子槽位，避免盟约成员引用悬空。
    for entry in entries.values():
        if entry["kind"] == "bond":
            entry["member_ids"] = [cid for cid in entry["member_ids"] if cid in entries]
            entry["members"] = [{"id": cid, "name": entries[cid]["name"]} for cid in entry["member_ids"] if cid in entries]
    return entries, aliases
