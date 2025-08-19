import logging

from typing import Annotated
from pydantic import Field
from src.server import mcp
from mcp.server.fastmcp import Context
from src.assets.gameData import GameData

logger = logging.getLogger("mcp_tool")


SPType = {
    'INCREASE_WITH_TIME': '自动回复',
    'INCREASE_WHEN_ATTACK': '攻击回复',
    'INCREASE_WHEN_TAKEN_DAMAGE': '受击回复',
    1: '自动回复',
    2: '攻击回复',
    4: '受击回复',
    8: '被动',
}

SkillType = {
    'PASSIVE': '被动',
    'MANUAL': '手动触发',
    'AUTO': '自动触发',
    0: '被动',
    1: '手动触发',
    2: '自动触发',
}

SkillLevel = {
    8: '专精一',
    9: '专精二',
    10: '专精三',
}


@mcp.tool(
    description='获取干员的技能数据，默认为第1个技能，等级10。如果需要计算具体数值，你可能还需要调用get_operator_basic来获取干员的基本信息。',
)
def get_operator_skill(
    operator_name: Annotated[str, Field(description='干员名')],
    operator_name_prefix: Annotated[str, Field(description='干员名的前缀，没有则为空')] = '',
    index: Annotated[int, Field(description='技能序号，默认为第1个')] = 1,
    level: Annotated[int, Field(description='技能等级，可为 1~10，其中等级8~10也被称为专精一、专精二和专精三')] = 10
) -> str:
    opt, operator_name = GameData.get_operator(operator_name, operator_name_prefix)

    if not opt:
        return f'未找到干员{operator_name}的技能资料'

    skills = opt.skills()

    if len(skills) < index:
        return f'干员{operator_name}没有第{index}个技能'

    skill = skills[index - 1]
    skill_desc = skill['skill_desc']

    if len(skill_desc) < level or 1 < level > 10:
        return f'干员{operator_name}的技能"%s"无法升级到等级{level}' % skill['skill_name']

    res = skill_desc[level - 1]

    retVal = '\n'.join(
        [
            f'干员{operator_name}的技能"%s"' % skill['skill_name'],
            '等级：' + (SkillLevel[level] if level >= 8 else str(level)),
            '技能范围：' + res['range'],
            SPType[res['sp_type']],
            SkillType[res['skill_type']],
            '技能效果：' + res['description'],
        ]
    )

    logger.info(retVal)

    return retVal
