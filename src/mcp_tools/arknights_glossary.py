import json
import logging

from typing import Annotated,List,Union
from pydantic import Field
from src.server import mcp
from src.assets.gameData import GameData
from src.assets.glossary_data import GLOSSARY as glossary

logger = logging.getLogger("mcp_tool")

@mcp.tool(
    description='获取明日方舟游戏数据中指定术语的解释和计算公式。例如你可以查询特定术语如"攻击力"来获取关于如何计算具体伤害的公式。',
)
def get_glossary(
    glossary_name: Annotated[Union[List[str], str], Field(description='要查询的术语名列表，可以是术语字符串、逗号/顿号分隔的术语字符串、或字符串数组')],
) -> str:
    """
    输入:
        - glossary_name: 可以是术语字符串、逗号/顿号分隔的术语字符串、或字符串数组
    输出:
        - JSON 字符串: { "术语名": "术语解释", ... }
    规则:
        1) 只要用户查询的术语中“包含” glossary 的术语（或反向包含以增强召回），就算匹配
        2) 如果某个术语解释文本中包含了其它 glossary 术语名，则级联把这些术语也加入返回结果
    """
    # 使用外部定义的 glossary
    global glossary
    if not isinstance(glossary, dict):
        return "{}"

    # 1) 归一化输入为术语列表
    terms: List[str] = []
    if isinstance(glossary_name, list):
        for item in glossary_name:
            if isinstance(item, str) and item.strip():
                terms.extend(split_terms(item))
    elif isinstance(glossary_name, str):
        terms = split_terms(glossary_name)
    else:
        return "{}"

    # 2) 先根据“包含关系”找到第一批命中的 glossary 术语
    matched = set()
    all_glossary_terms = list(glossary.keys())

    for q in terms:
        for g in all_glossary_terms:
            # 规则 3: 只要查询项包含 glossary 术语就算命中
            # 同时加上反向包含 (q in g) 以提升宽容度，例如用户输入“物理攻击力”，则同时命中攻击力和物理攻击
            if g in q or q in g:
                matched.add(g)

    # 3) 级联：若解释文本中出现其它 glossary 术语，也要纳入
    # 反复迭代直到不再有新增（避免遗漏多层依赖）
    changed = True
    while changed:
        changed = False
        current = list(matched)
        for term in current:
            explain = glossary.get(term, "") or ""
            for g in all_glossary_terms:
                if g in explain and g not in matched:
                    matched.add(g)
                    changed = True

    # 4) 组织结果并返回 JSON 字符串（保留中文）
    result = {t: glossary[t] for t in all_glossary_terms if t in matched}
    retVal = json.dumps(result, ensure_ascii=False)
    
    logger.info(f"{retVal}")
    return retVal


def split_terms(s: str) -> List[str]:
    """
    将输入字符串按常见中文/英文分隔符切分为术语列表，并去除空白。
    支持: 逗号(, ,，)、顿号(、)、分号(;；)、空白
    """
    if not isinstance(s, str):
        return []
    for sep in ["，", ",", "、", ";", "；"]:
        s = s.replace(sep, " ")
    parts = [p.strip() for p in s.split() if p.strip()]
    return parts