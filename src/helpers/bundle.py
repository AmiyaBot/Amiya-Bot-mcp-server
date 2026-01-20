import re
import difflib
from typing import Any, Optional, Mapping, Sequence

# 该文件里放置了不需要领域模型的一些辅助函数

_PUNCT_RE = re.compile(r"[^\w\u4e00-\u9fff]+")

def get_table(tables: Mapping[str, Mapping[str, Any]], name: str, *, source="gamedata", default=None):
    return tables.get(source, {}).get(name, default)

def remove_punctuation(s: str) -> str:
    if not s:
        return ""
    return _PUNCT_RE.sub("", s)

def html_tag_format(text: Optional[str]) -> str:
    # 旧项目里是 remove_xml_tag + html_symbol 替换，这里做一个最小实现
    if not text:
        return ""
    # 去掉简单 xml 标签
    return re.sub(r"<[^>]+>", "", text)

def integer(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v).strip()
        if not s:
            return None
        return int(float(s))
    except Exception:
        return None

def find_most_similar(text: str, text_list: Sequence[str]) -> Optional[str]:
    res = find_similar_list(text, text_list)
    if res:
        return res[0]

def find_longest(text: str, items: Sequence[str]) -> Optional[str]:
    res = ''
    for item in items:
        if item in text and len(item) >= len(res):
            res = item

    return res

def find_similar_list(text: str, text_list: Sequence[str]) -> list[str]:
    result = {}
    for item in text_list:
        rate = float(difflib.SequenceMatcher(None, text, item).quick_ratio() * len([n for n in text if n in set(item)]))
        if rate > 0:
            if rate not in result:
                result[rate] = []
            result[rate].append(item)

    if result:
        return result[sorted(result.keys())[-1]]
    return []

def parse_template(blackboard: list, description: str) -> str:
    """
    贴近你旧项目逻辑：把 {key} / {key:0%} 替换成 blackboard 里的值。
    """
    if not description:
        return ""
    formatter = {"0%": lambda v: f"{round(v * 100)}%"}
    data_dict = {item["key"]: item.get("valueStr") or item.get("value") for item in blackboard or []}

    desc = html_tag_format(description.replace(">-{", ">{"))
    format_str = re.findall(r"({(\S+?)})", desc)
    if format_str:
        for token, inner in format_str:
            key = inner.split(":")
            fd = key[0].lower().strip("-")
            if fd in data_dict:
                value = integer(data_dict[fd])
                if len(key) >= 2 and key[1] in formatter and value is not None:
                    value = formatter[key[1]](value)
                desc = desc.replace(token, str(value) if value is not None else "")
    return desc

def build_range(grids: list) -> str:
    if not grids:
        return "无范围"
    _max = [0, 0, 0, 0]
    for item in [{"row": 0, "col": 0}] + grids:
        row, col = item["row"], item["col"]
        if row <= _max[0]:
            _max[0] = row
        if row >= _max[1]:
            _max[1] = row
        if col <= _max[2]:
            _max[2] = col
        if col >= _max[3]:
            _max[3] = col

    width = abs(_max[2]) + _max[3] + 1
    height = abs(_max[0]) + _max[1] + 1

    empty, block, origin = "　", "□", "■"
    range_map = [[empty for _ in range(width)] for _ in range(height)]
    for item in grids:
        x = abs(_max[0]) + item["row"]
        y = abs(_max[2]) + item["col"]
        range_map[x][y] = block
    range_map[abs(_max[0])][abs(_max[2])] = origin
    return "".join(["".join(row) + "\n" for row in range_map])