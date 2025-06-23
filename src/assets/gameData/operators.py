from src.assets import JsonData
from src.assets.convert import parse_template, integer


class Operator:
    def __init__(self, code: str, data: dict):
        self.code = code
        self.data = data

        self.range = self.__range()

    def __range(self):
        range_data = JsonData.get_json_data('range_table')
        range_id = self.data['phases'][-1]['rangeId']
        if range_id in range_data:
            return build_range(range_data[range_id]['grids'])
        return ''

    def skills(self):
        skill_data = JsonData.get_json_data('skill_table')
        range_data = JsonData.get_json_data('range_table')

        result = []
        default_skills_cost = []

        skill_level_up_data = self.data['allSkillLvlup']
        if skill_level_up_data:
            for index, item in enumerate(skill_level_up_data):
                if item['lvlUpCost']:
                    for cost in item['lvlUpCost']:
                        default_skills_cost.append(
                            {
                                'skill_no': None,
                                'level': index + 2,
                                'mastery_level': 0,
                                'use_material_id': cost['id'],
                                'use_number': cost['count'],
                            }
                        )

        for index, item in enumerate(self.data['skills']):
            code = item['skillId']
            detail = skill_data.get(code)

            if not detail:
                continue

            skill_item = {
                'skill_id': code,
                'skill_index': index + 1,
                'skill_name': detail['levels'][0]['name'],
                'skill_icon': detail['iconId'] or detail['skillId'],
                'skill_desc': [],
                'skills_cost': [*default_skills_cost],
            }

            for lev, desc in enumerate(detail['levels']):
                description = parse_template(desc['blackboard'], desc['description'])

                skill_range = self.range
                if desc['rangeId'] in range_data:
                    skill_range = build_range(range_data[desc['rangeId']]['grids'])

                skill_item['skill_desc'].append(
                    {
                        'skill_level': lev + 1,
                        'skill_type': desc['skillType'],
                        'sp_type': desc['spData']['spType'],
                        'sp_init': desc['spData']['initSp'],
                        'sp_cost': desc['spData']['spCost'],
                        'duration': integer(desc['duration']),
                        'description': description.replace('\\n', '\n'),
                        'max_charge': desc['spData']['maxChargeTime'],
                        'range': skill_range,
                    }
                )

            level_up_cost_data = ''
            if 'specializeLevelUpData' in item:
                level_up_cost_data = item['specializeLevelUpData']
            elif 'levelUpCostCond' in item:
                level_up_cost_data = item['levelUpCostCond']

            for lev, cond in enumerate(level_up_cost_data):
                if bool(cond['levelUpCost']) is False:
                    continue

                for idx, cost in enumerate(cond['levelUpCost']):
                    skill_item['skills_cost'].append(
                        {
                            'skill_id': code,
                            'level': lev + 8,
                            'mastery_level': lev + 1,
                            'use_material_id': cost['id'],
                            'use_number': cost['count'],
                        }
                    )

            result.append(skill_item)

        return result


class Operators:
    def __init__(self):
        self.character_table = JsonData.get_json_data('character_table')
        self.operator_map = {item['name']: code for code, item in self.character_table.items()}

    def get_operator(self, name: str) -> Operator | None:
        if name in self.operator_map:
            code = self.operator_map[name]
            return Operator(code, self.character_table[code])


def build_range(grids):
    if not grids:
        return ''

    min_row = min(g['row'] for g in grids)
    max_row = max(g['row'] for g in grids)
    min_col = min(g['col'] for g in grids)
    max_col = max(g['col'] for g in grids)

    width = max_col - min_col + 1
    height = max_row - min_row + 1

    empty = '　'
    block = '□'
    origin = '■'
    range_map = [[empty for _ in range(width)] for _ in range(height)]

    origin_x = -min_row
    origin_y = -min_col
    range_map[origin_x][origin_y] = origin

    for grid in grids:
        x = grid['row'] - min_row
        y = grid['col'] - min_col
        range_map[x][y] = block

    return '\n'.join(''.join(row) for row in range_map)
