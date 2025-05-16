import os
import json

from src.server import mcp

folder = r'E:\AI-assets\dist'


@mcp.tool()
def get_operator_skill(operator_name: str, index: int = 1) -> str:
    """
    获取干员的技能数据，默认为第一个技能

    :param operator_name: 干员名
    :param index: 技能序号，默认为第一个，即 1
    :return: 技能数据
    """
    with open(f'{folder}/skills-single.json', mode='r', encoding='utf-8') as f:
        opt_map = json.load(f)

    opt_file = f'{operator_name}.txt'

    if opt_file in opt_map:
        path = os.path.join(folder, 'skills-single', opt_file)

        with open(path, mode='r', encoding='utf-8') as f:
            content = [n.strip('\n') for n in f.read().split('===separator===')]

        return content[index - 1]
    else:
        return f'未找到干员{operator_name}的技能资料'
