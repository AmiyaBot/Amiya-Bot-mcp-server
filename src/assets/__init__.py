import os
import re
import json

AssetsPath = r'E:\Production\amiya-bot\amiya-bot-assets'

html_symbol = {'<替身>': '&lt;替身&gt;', '<支援装置>': '&lt;支援装置&gt;'}


class JsonData:
    cache = {}

    @classmethod
    def get_json_data(cls, name: str, folder: str = 'excel'):
        if name not in cls.cache:
            path = f'{AssetsPath}/gamedata/{folder}/{name}.json'
            if os.path.exists(path):
                with open(path, mode='r', encoding='utf-8') as src:
                    cls.cache[name] = json.load(src)
            else:
                return {}

        return cls.cache[name]

    @classmethod
    def clear_cache(cls, name: str = None):
        if name:
            del cls.cache[name]
        else:
            cls.cache = {}


def parse_template(blackboard: list, description: str):
    formatter = {'0%': lambda v: f'{round(v * 100)}%'}
    data_dict = {item['key']: item.get('valueStr') or item.get('value') for index, item in enumerate(blackboard)}

    desc = html_tag_format(description.replace('>-{', '>{'))
    format_str = re.findall(r'({(\S+?)})', desc)
    if format_str:
        for desc_item in format_str:
            key = desc_item[1].split(':')
            fd = key[0].lower().strip('-')
            if fd in data_dict:
                value = integer(data_dict[fd])

                if len(key) >= 2 and key[1] in formatter and value:
                    value = formatter[key[1]](value)

                desc = desc.replace(desc_item[0], str(value))

    return desc


def html_tag_format(text: str):
    if text is None:
        return ''

    for o, f in html_symbol.items():
        text = text.replace(o, f)

    return remove_xml_tag(text)


def integer(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def remove_xml_tag(text: str):
    return re.compile(r'<[^>]+>', re.S).sub('', text)
