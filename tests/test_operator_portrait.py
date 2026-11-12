import asyncio
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.app.config import Config
from src.app.renderers.jinja_html_renderer import JinjaHtmlRenderer
from src.app.renderers.jinja_template_loader import JinjaTemplateLoader
from src.app.services import operator_queries
from src.data.repository.bundle.bundle_builder import load_bundle_from_disk
from src.domain.services.operator import build_operator_query_result

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def bundle():
    return load_bundle_from_disk(Config(ROOT, ROOT / 'resources', GameDataRepo='test'), version='portrait-test')


def context():
    return SimpleNamespace(cfg=Config(ROOT, ROOT / 'resources', BaseUrl='https://example.test/'),
                           data_repository=SimpleNamespace(get_bundle=bundle))


@pytest.mark.parametrize('name', ['缪尔赛思', '阿米娅', 'Lancet-2'])
def test_portrait_renders_real_operators(name):
    op = next(op for op in bundle().operators.values() if op.name == name)
    result = build_operator_query_result(context(), op)
    html = JinjaHtmlRenderer(JinjaTemplateLoader(str(ROOT / 'data/templates'))).render('operator_info_portrait', result).payload
    assert op.name in html
    assert 'RHODES ISLAND' in html
    assert '基础属性' in html
    assert '原图裁切预览' not in html
    assert 'setScale' not in html
    if not op.skills:
        assert '<h2>战斗技能</h2>' not in html


def test_switch_changes_template_url_and_cache_without_changing_data(monkeypatch, tmp_path):
    ctx = context()
    ctx.card_service = SimpleNamespace(cache_root=tmp_path, get=AsyncMock(return_value=SimpleNamespace(path=tmp_path / 'card.png')))
    monkeypatch.setattr(operator_queries, 'resolve_operator_skin_artifact', AsyncMock(return_value=None))
    op = next(op for op in bundle().operators.values() if op.name == 'Lancet-2')
    outputs = []
    calls = []
    for enabled in (True, False):
        ctx.cfg.PortraitAttributeCardEnabled = enabled
        outputs.append(asyncio.run(operator_queries.query_operator_basic_by_id(ctx, op.id)))
        calls.append(ctx.card_service.get.call_args.kwargs)
        assert operator_queries.resolve_operator_skin_artifact.call_args.kwargs['prefer_elite_two'] is enabled
    assert outputs[0].data == outputs[1].data
    assert calls[0]['template'] == 'operator_info_portrait'
    assert calls[1]['template'] == 'operator_info'
    assert calls[0]['payload_key'] != calls[1]['payload_key']
    assert '/operator_info_portrait/' in outputs[0].image_url
    assert '/operator_info/' in outputs[1].image_url


def test_portrait_preserves_chess_variants_and_escapes_text():
    op = next(op for op in bundle().operators.values() if op.name == '缪尔赛思')
    result = build_operator_query_result(context(), op)
    result.data['autochess'] = {
        'title': '卫戍协议 · 规程', 'tier': 6,
        'bonds': [{'name': '盟约', 'icon': ''}],
        'variants': [{'name': '普通', 'price': 0, 'description': '<测试>普通效果'},
                     {'name': '精锐', 'price': 0, 'description': '精锐效果'}],
    }
    html = JinjaHtmlRenderer(JinjaTemplateLoader(str(ROOT / 'data/templates'))).render('operator_info_portrait', result).payload
    assert 'AUTOCHESS' in html
    assert '棋子等阶 VI' in html
    assert '价格 0' in html
    assert '<span class="chess-condition">测试</span>普通效果' in html
    assert html.count('价格 0') == 1
    assert 'class="chess-heading"' in html
    assert '精锐效果' in html
