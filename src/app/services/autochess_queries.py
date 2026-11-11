# AI-REMOVED 2026-11-10:
# Reason: 用户仅授权结构化数据，撤回未经授权的卫戍协议查询和卡片接入。
# Trigger: 用户要求先去掉本次新增接口，后续按指导梳理添加。
# Evidence: 本次工作区 diff 中新增的卫戍协议工具、搜索和卡片代码。
# Replacement: None；仅保留 src/data/repository/bundle/autochess.py 数据结构化。
# Risk: Low；既有查询入口保持原行为。
# Human Review: Required
# Original code:
# from __future__ import annotations
#
# from copy import deepcopy
# import hashlib
# import json
# import logging
#
# from src.app.services.operator_queries import QueryExecutionResult
# from src.domain.services.operator import build_operator_template_font_url
# from src.domain.types import QueryResult
# from src.helpers.card_urls import build_card_url
#
# logger = logging.getLogger(__name__)
#
# 
# async def query_autochess_detail(context, entry_id: str) -> QueryExecutionResult:
#     normalized_id = str(entry_id or "").strip()
#     if not normalized_id:
#         return QueryExecutionResult(message="entry_id 不能为空")
#     bundle = context.data_repository.get_bundle()
#     entry = (getattr(bundle, "autochess_entries", {}) or {}).get(normalized_id)
#     if entry is None:
#         return QueryExecutionResult(message=f"未找到卫戍协议资料ID: {normalized_id}")
#     payload = deepcopy(entry)
#     result = QueryExecutionResult(data=payload)
#     card = QueryResult(type="autochess", key=normalized_id, title=entry["name"], data={
#         "entry": payload,
#         "template_font_url": build_operator_template_font_url(context.cfg.ProjectRoot),
#     })
#     fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
#     cache_key = f"autochess-v1-{fingerprint}"
#     for output_format in ("json", "png"):
#         try:
#             artifact = await context.card_service.get(
#                 template="autochess", payload_key=cache_key, payload=card, format=output_format,
#                 params={"viewport": {"width": 1000, "height": 700}, "full_page": True, "wait_until": "load"},
#             )
#             if output_format == "png" and getattr(context, "prefer_local_artifact_path", False):
#                 result.image_path = str(artifact.path)
#             if getattr(context.cfg, "BaseUrl", None):
#                 url = build_card_url(cfg=context.cfg, template="autochess", payload_key=cache_key, format=output_format)
#                 if output_format == "png":
#                     result.image_url = url
#                 else:
#                     result.data_url = url
#         except Exception:
#             logger.warning("卫戍协议资料产物生成失败，保留结构化数据: id=%s format=%s", normalized_id, output_format, exc_info=True)
#     return result
