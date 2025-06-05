import re

from typing import Annotated
from pydantic import Field
from src.server import mcp
from src.assets import JsonData, html_tag_format
from src.assets.gameData import GameData


class GameDict:
    classes = {
        'CASTER': '术师',
        'MEDIC': '医疗',
        'PIONEER': '先锋',
        'SNIPER': '狙击',
        'SPECIAL': '特种',
        'SUPPORT': '辅助',
        'TANK': '重装',
        'WARRIOR': '近卫',
    }
    token_classes = {
        'TOKEN': '召唤物',
        'TRAP': '装置',
    }
    high_star = {
        '5': '资深干员',
        '6': '高级资深干员',
    }
    types = {
        'ALL': '不限部署位',
        'MELEE': '近战位',
        'RANGED': '远程位',
    }
    html_symbol = {
        '<替身>': '替身',
        '<支援装置>': '支援装置',
    }
    sp_type = {
        'INCREASE_WITH_TIME': '自动回复',
        'INCREASE_WHEN_ATTACK': '攻击回复',
        'INCREASE_WHEN_TAKEN_DAMAGE': '受击回复',
        1: '自动回复',
        2: '攻击回复',
        4: '受击回复',
        8: '被动',
    }
    skill_type = {
        'PASSIVE': '被动',
        'MANUAL': '手动触发',
        'AUTO': '自动触发',
        0: '被动',
        1: '手动触发',
        2: '自动触发',
    }
    skill_level = {
        1: '等级1',
        2: '等级2',
        3: '等级3',
        4: '等级4',
        5: '等级5',
        6: '等级6',
        7: '等级7',
        8: '等级8（专精1）',
        9: '等级9（专精2）',
        10: '等级10（专精3）',
    }
    attrs = {
        'maxHp': '最大生命值',
        'atk': '攻击力',
        'def': '防御力',
        'magicResistance': '魔法抗性',
        'attackSpeed': '攻击速度',
        'baseAttackTime': '攻击间隔',
        'blockCnt': '阻挡数',
        'cost': '部署费用',
        'respawnTime': '再部署时间',
    }
    attrs_unit = {
        'baseAttackTime': '秒',
        'respawnTime': '秒',
    }


@mcp.tool(
    description='获取干员的基础信息和属性',
)
def get_operator_basic(
    operator_name: Annotated[str, Field(description='干员名')],
    operator_name_prefix: Annotated[str, Field(description='干员名的前缀，没有则为空')] = '',
) -> str:
    team_table = JsonData.get_json_data('handbook_team_table')
    sub_classes = JsonData.get_json_data('uniequip_table')['subProfDict']

    opt, operator_name = GameData.get_operator(operator_name, operator_name_prefix)
    char = opt.data
    char_name = char['name']

    if not opt:
        return f'未找到干员{operator_name}的资料'

    char_desc = html_tag_format(char['description'])

    classes = GameDict.classes[char['profession']]
    classes_sub = sub_classes[char['subProfessionId']]['subProfessionName']

    if classes_sub == '驭械术师':
        char_desc = '初始携带1个浮游单元，浮游单元初始造成相当于干员攻击力20%的法术伤害，每次对上次攻击的同一目标进行攻击时该数值增加15，上限110%（即通常情况下需叠加6次才能达到上限）。'

    group_id = char['groupId']
    group = team_table[group_id]['powerName'] if group_id in team_table else '无'

    max_phases = char['phases'][-1]
    max_attr = max_phases['attributesKeyFrames'][-1]['data']

    content = f'{char_name}\n职业：{classes_sub}（{classes}），{char_desc}\n阵营：{group}\n' + '\n'.join(
        [f'{n}：{max_attr[k]}%s' % GameDict.attrs_unit.get(k, '') for k, n in GameDict.attrs.items()]
    )

    talents = []
    if char['talents']:
        for index, item in enumerate(char['talents']):
            max_item = item['candidates'][-1]
            if max_item['name']:
                text = '第%d天赋：%s，效果为%s。' % (
                    index + 1,
                    max_item['name'],
                    html_tag_format(max_item['description']),
                )
                text = re.sub(r'（[+-]\d+(\.\d+)?%?）', '', text)
                text = re.sub(r'\([+-]\d+(\.\d+)?%?\)', '', text)

                talents.append(text)

    content += ('\n\n' + '\n'.join(talents)) if talents else ''

    return content
