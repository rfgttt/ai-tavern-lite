from app.services.runtime.output_parser import parse_runtime_output
from app.services.tavern_compat.paths import normalize_card_pointer


def test_normalizes_platform_and_card_variable_roots():
    assert normalize_card_pointer('/scene/location') == '/scene/location'
    assert normalize_card_pointer('/关系/好感度') == '/relationship/好感度'
    assert normalize_card_pointer('/stat_data/雾叶泠/好感度') == '/custom/雾叶泠/好感度'
    assert normalize_card_pointer('/variables/world/time') == '/custom/world/time'
    assert normalize_card_pointer('/雾叶泠/好感度') == '/custom/雾叶泠/好感度'
    assert normalize_card_pointer('/custom/世界信息/当前地点') == '/custom/世界信息/当前地点'
    assert normalize_card_pointer('/custom/场景/地点') == '/scene/地点'


def test_preserves_json_pointer_escaping():
    assert normalize_card_pointer('/角色/a~1b/~0flag') == '/character/a~1b/~0flag'
    assert normalize_card_pointer('/奇怪~1根/value') == '/custom/奇怪~1根/value'


def test_runtime_parser_normalizes_path_and_from():
    parsed = parse_runtime_output('''
正文
<UpdateVariable><JSONPatch>
[
  {"op":"replace","path":"/世界信息/当前地点","value":"屋顶"},
  {"op":"move","from":"/stat_data/背包/旧物","path":"/inventory/-"}
]
</JSONPatch></UpdateVariable>
''')
    assert parsed.patch[0]['path'] == '/custom/世界信息/当前地点'
    assert parsed.patch[1]['from'] == '/custom/背包/旧物'
    assert parsed.patch[1]['path'] == '/inventory/-'
