from app.services.cards.compatibility import build_compatibility_report
from app.services.runtime.card_profile import analyze_card


def complex_card():
    return {
        'spec': 'chara_card_v3',
        'spec_version': '3.0',
        'name': '通用复杂卡',
        'first_mes': '你好 <user>\n\n<StatusPlaceHolderImpl/>',
        'extensions': {
            'tavern_helper': {
                'scripts': [
                    {'name': 'MVU-zod', 'enabled': True, 'content': "import 'https://cdn.example/mvu.js';"},
                ],
                'variables': {},
            },
            'regex_scripts': [
                {'scriptName': '状态栏正则', 'findRegex': '<StatusPlaceHolderImpl/>', 'replaceString': '<script>x()</script>'},
            ],
        },
        'character_book': {
            'entries': [
                {'comment': '[initvar]', 'enabled': False, 'content': '角色:\n  好感度: 20'},
                {'comment': '变量规则', 'enabled': True, 'constant': True, 'content': '{{format_message_variable::stat_data}} <UpdateVariable><JSONPatch>'},
            ]
        },
    }


def test_report_distinguishes_detected_protocol_from_runtime_usability():
    report = build_compatibility_report(complex_card())

    assert report['version'] == 4
    assert report['runtime_checks']['initial_variables']['status'] == 'supported'
    assert report['runtime_checks']['initial_variables']['source'] == 'worldbook:[initvar]'
    assert report['runtime_checks']['patch_paths']['status'] == 'supported'
    assert report['runtime_checks']['read_only_macros']['status'] == 'supported'
    assert report['runtime_checks']['status_placeholder']['status'] == 'supported'
    assert report['runtime_checks']['external_javascript']['status'] == 'isolated'
    mvu = next(item for item in report['details'] if item['key'] == 'mvu')
    assert mvu['status'] == 'supported'
    assert '初始化' in mvu['summary']


def test_mvu_without_initial_variables_is_only_partial():
    report = build_compatibility_report({
        'name': '缺少初始化',
        'extensions': {},
        'character_book': {'entries': [
            {'comment': '变量规则', 'enabled': True, 'content': '<UpdateVariable><JSONPatch>'},
        ]},
    })
    mvu = next(item for item in report['details'] if item['key'] == 'mvu')
    assert mvu['status'] == 'partial'
    assert report['runtime_checks']['initial_variables']['status'] == 'absent'


def test_runtime_profile_version_advances_for_existing_cards():
    profile = analyze_card(complex_card())
    assert profile['version'] == 8
    assert profile['compatibility_core'] == 'tavern-safe-v6'
