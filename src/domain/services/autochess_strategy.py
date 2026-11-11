"""当期策略的查询资料；保留完整文案，不推算技能效果。"""
from src.domain.services.autochess_bond import current_autochess_version


def current_strategies(bundle, *, now=None):
    version = current_autochess_version(bundle, now=now)
    if not version:
        return {}
    return {key: entry for key, entry in (getattr(bundle, 'autochess_entries', {}) or {}).items()
            if entry.get('kind') == 'strategy' and entry.get('ruleset') == 'standard'
            and entry.get('activity_id') == version.get('activityId')
            and entry.get('version_id') == version.get('versionId')}


def strategy_search_item(entry):
    return {'id': entry['id'], 'name': entry['name'], 'type': '卫戍协议策略',
            'activity_name': entry['activity_name'].replace(':', '：'),
            'owner_name': entry.get('owner_name', '')}


def strategy_detail(entry):
    skills = []
    for skill in entry.get('skills') or []:
        item = {'类型': {'ACTIVE': '主动', 'PASSIVE': '被动', 'NONE': '状态说明'}.get(skill.get('type'), '技能说明'),
                '描述': skill.get('description') or ''}
        if skill.get('type') == 'ACTIVE':
            if skill.get('cost') is not None:
                item['费用'] = skill['cost']
            count = skill.get('usage_count')
            scope = {'ROUND_RESET': '每回合', 'ALL_LIMIT': '整局'}.get(skill.get('usage_type'))
            if scope and count is not None and count > 0:
                item['使用限制'] = f'{scope}限{count}次'
        if item not in skills:
            skills.append(item)
    return {'ID': entry['id'], '卫戍协议': entry['activity_name'].replace(':', '：'),
            '名称': entry['name'], '发起人': entry.get('owner_name') or '',
            '说明': entry.get('description') or '', '技能': skills,
            '解锁条件': entry.get('unlock_description') or '暂无解锁条件说明'}


def strategy_display(detail):
    """仅合并正文被总述完整包含的重复块；结构化输出仍保留原文。"""
    import re

    def body(text):
        text = re.sub(r'^【[^\n]+】\s*\n', '', text.strip())
        return re.sub(r'（消耗\d+）', '', text).strip()

    overview = detail['说明']
    skills = [dict(skill) for skill in detail['技能']]
    actionable = [s for s in skills if s['类型'] in ('主动', '被动')]
    if len(actionable) == 1 and body(actionable[0]['描述']) and body(actionable[0]['描述']) in body(overview):
        primary = actionable[0]
        primary['描述'] = overview
        skills = [s for s in skills if s is primary or not (body(s['描述']) and body(s['描述']) in body(overview))]
        overview = ''
    elif overview.strip() in [s['描述'].strip() for s in skills]:
        overview = ''
    return overview, skills
