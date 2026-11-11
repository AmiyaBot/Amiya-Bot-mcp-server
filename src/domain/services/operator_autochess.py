"""干员角色卡的当期棋子信息；不提供独立查询入口。"""
from __future__ import annotations

from src.domain.services.autochess_bond import current_autochess_version

import base64
from datetime import datetime, timezone
from pathlib import Path


def build_operator_autochess(bundle, operator_id: str, project_root: Path, *, now=None):
    # 2026-11-11: 当期判定迁至 current_autochess_version，供角色卡与盟约查询共享。
    current = current_autochess_version(bundle, now=now)
    if not current:
        return None
    entry = next((e for e in (getattr(bundle, "autochess_entries", {}) or {}).values()
                  if e.get("kind") == "chess" and e.get("ruleset") == "standard"
                  and e.get("operator_id") == operator_id
                  and e.get("activity_id") == current.get("activityId")
                  and e.get("version_id") == current.get("versionId")), None)
    if not entry:
        return None
    assets = project_root / "data/templates/operator_info/assets/autochess"

    def icon(name):
        path = assets / name
        if not path.is_file():
            return ""
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    variants = []
    bonds = {}
    for variant in entry.get("variants") or []:
        for bond in variant.get("bonds") or []:
            bonds[bond["source_id"]] = {
                "name": bond["name"], "icon": icon(f"icon_{bond['source_id']}.png"),
            }
        description = variant.get("description") or ""
        extras = [t["description"] for t in variant.get("traits") or []
                  if t.get("description") and t["description"] not in description]
        # 棋子 desc 是完整展示文案；底层特质可带额外事件前缀，不能重复拼接。
        text = (description or "\n".join(dict.fromkeys(extras))).strip()
        if text:
            variants.append({"name": variant["name"], "description": text,
                             "price": variant.get("purchase_price")})
    if not bonds or not variants:
        return None
    if len(variants) == 2 and variants[0]["description"] == variants[1]["description"] and variants[0]["price"] == variants[1]["price"]:
        variants = [{**variants[0], "name": "普通 / 精锐"}]
    title = entry["activity_name"].replace(":", "：") + " 棋子信息"
    return {"title": title, "tier": entry["tier"], "bonds": list(bonds.values()),
            "variants": variants, "coin_icon": icon("s_icon_gold.png"),
            "common_price": len({v["price"] for v in variants}) == 1}

# AI-REMOVED 2026-11-11:
# Reason: 提取共享当期判定。Trigger: 新增当期盟约查询。
# Evidence: 两种卡片须采用同一档期。Replacement: autochess_bond.current_autochess_version。
# Risk: Low。Human Review: Required
#     table = ((getattr(bundle, "tables", {}) or {}).get("gamedata") or {}).get("activity_table") or {}
#     versions = (table.get("autoChessData") or {}).get("versionInfoDict") or {}
#     timestamp = (now or datetime.now(timezone.utc)).timestamp()
#     active = [v for v in versions.values()
#               if v.get("startTime", 0) <= timestamp < v.get("endTime", 0)
#               and not v.get("isOffseason")]
#     if not active:
#         return None
#     current = max(active, key=lambda v: (v.get("startTime", 0), v.get("versionId", "")))
