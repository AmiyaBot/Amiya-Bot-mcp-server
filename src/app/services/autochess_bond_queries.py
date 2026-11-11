from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path

from src.app.context import get_bundle_resource_root
from src.app.services.operator_queries import QueryExecutionResult
from src.domain.services.autochess_bond import current_bonds, bond_detail
from src.domain.services.operator import build_operator_template_font_url
from src.domain.types import QueryResult
from src.helpers.card_urls import build_card_url

logger = logging.getLogger(__name__)


def bond_icon_path(project_root, entry):
    return Path(project_root) / 'data/templates/operator_info/assets/autochess' / f"icon_{entry['source_id']}.png"


def image_uri(path):
    return 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode() if path.is_file() else ''


async def query_autochess_bond_detail(context, bond_id):
    bundle = context.data_repository.get_bundle()
    entry = current_bonds(bundle).get(str(bond_id or '').strip())
    if entry is None:
        return QueryExecutionResult(message='未找到当期盟约，请先通过 search 获取盟约 ID')
    detail = bond_detail(bundle, entry)
    root = get_bundle_resource_root(bundle, context)
    members = [{**member, 'avatar': image_uri(root / 'assets/avatar' / f"{member['干员ID']}#1.png")}
               for member in detail['所属棋子']]
    payload = QueryResult(type='autochess_bond', key=entry['id'], title=entry['name'], data={
        'detail': detail, 'members': members,
        'icon': image_uri(bond_icon_path(context.cfg.ProjectRoot, entry)),
        'template_font_url': build_operator_template_font_url(context.cfg.ProjectRoot),
    })
    digest = hashlib.sha256(json.dumps(payload.data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    key = f"bond-v4:{digest}"
    result = QueryExecutionResult(data=detail)
    try:
        artifact = await context.card_service.get(template='autochess_bond', payload_key=key, payload=payload,
            format='png', params={'viewport': {'width': 1080, 'height': 600}, 'full_page': True})
        if getattr(context, 'prefer_local_artifact_path', False):
            result.image_path = str(artifact.path)
        if context.cfg.BaseUrl:
            result.image_url = build_card_url(cfg=context.cfg, template='autochess_bond', payload_key=key, format='png')
    except Exception:
        logger.exception('盟约卡片生成失败: %s', bond_id)
        result.message = '盟约卡片生成失败，已保留完整文字资料'
    return result
