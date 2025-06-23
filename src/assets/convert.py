import re


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

    html_symbol = {
        '<替身>': '&lt;替身&gt;',
        '<支援装置>': '&lt;支援装置&gt;',
    }
    for o, f in html_symbol.items():
        text = text.replace(o, f)

    return remove_xml_tag(text)


def integer(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def remove_xml_tag(text: str):
    return re.compile(r'<[^>]+>', re.S).sub('', text)
