from src.app.services.operator_skin_assets import _select_portrait_skin_entry, _select_skin_entry


def tables(mapping):
    return {'gamedata': {'skin_table': {'buildinEvolveMap': {'char_test': mapping}}}}


def test_elite_two_mapping_wins_without_changing_legacy_selection():
    urls = {'char_test@shop#2': 'shop', 'char_test#1': 'base', 'char_test#1+': 'elite1', 'char_test#2': 'elite2'}
    data = tables({'0': 'char_test#1', '1': 'char_test#1+', '2': 'char_test#2'})
    assert _select_portrait_skin_entry('char_test', urls, data) == ('char_test#2', 'elite2')
    assert _select_skin_entry('char_test', urls, data) == ('char_test#1', 'base')


def test_low_star_and_missing_elite_image_use_base():
    urls = {'char_test@shop#2': 'shop', 'char_test#1': 'base'}
    for mapping in ({'0': 'char_test#1'}, {'0': 'char_test#1', '2': 'char_test#2'}, {}):
        assert _select_portrait_skin_entry('char_test', urls, tables(mapping)) == ('char_test#1', 'base')


def test_no_named_skin_or_other_operator_fallback():
    urls = {'char_test@shop#2': 'shop', 'char_other#2': 'other'}
    for mapping in ({}, {'2': 'char_test@shop#2'}, {'2': 'char_other#2'}):
        assert _select_portrait_skin_entry('char_test', urls, tables(mapping)) is None
