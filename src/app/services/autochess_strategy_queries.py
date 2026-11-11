from __future__ import annotations

import hashlib
import json
import logging

from src.app.services.autochess_bond_queries import image_uri
from src.app.services.autochess_strategy_assets import strategy_portrait_path
from src.app.services.operator_queries import QueryExecutionResult
from src.domain.services.autochess_strategy import current_strategies, strategy_detail, strategy_display
from src.domain.services.operator import build_operator_template_font_url
from src.domain.types import QueryResult
from src.helpers.card_urls import build_card_url

logger = logging.getLogger(__name__)


async def query_autochess_strategy_detail(context, strategy_id):
    bundle = context.data_repository.get_bundle()
    entry = current_strategies(bundle).get(str(strategy_id or '').strip())
    if entry is None:
        return QueryExecutionResult(message='未找到当期策略，请先通过 search 获取策略 ID')
    detail = strategy_detail(entry)
    # 2026-11-11: 展示层合并被总述完整覆盖的技能正文，保留条件变化。
    overview, display_skills = strategy_display(detail)
    payload = QueryResult(type='autochess_strategy', key=entry['id'], title=entry['name'], data={
        'detail': detail, 'overview': overview, 'display_skills': display_skills,
        'portrait': image_uri(strategy_portrait_path(context.cfg.ProjectRoot, entry)),
        'template_font_url': build_operator_template_font_url(context.cfg.ProjectRoot),
    })
    digest = hashlib.sha256(json.dumps(payload.data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    key = f'strategy-v3:{digest}'
    result = QueryExecutionResult(data=detail)
    try:
        artifact = await context.card_service.get(template='autochess_strategy', payload_key=key, payload=payload,
            format='png', params={'viewport': {'width': 1080, 'height': 600}, 'full_page': True})
        if getattr(context, 'prefer_local_artifact_path', False):
            result.image_path = str(artifact.path)
        if context.cfg.BaseUrl:
            result.image_url = build_card_url(cfg=context.cfg, template='autochess_strategy', payload_key=key, format='png')
    except Exception:
        logger.exception('策略卡片生成失败: %s', strategy_id)
        result.message = '策略卡片生成失败，已保留完整文字资料'
    return result

# AI-REMOVED 2026-11-11:
# Reason: 原判重遗漏总述覆盖技能正文的情况。Trigger: 策略卡重复展示。
# Evidence: 黑白相易、出航时刻截图。Replacement: strategy_display。Risk: Low。Human Review: Required
#     # 仅当总述和技能文案完全相同时省略重复展示；条件、变体一律保留。
#     overview = detail['说明']
#     if overview.strip() in [s['描述'].strip() for s in detail['技能']]:
#         overview = ''
