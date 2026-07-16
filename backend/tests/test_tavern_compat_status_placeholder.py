from app.services.rendering.message_ast import parse_message_ast


def test_status_placeholder_becomes_native_ast_segment():
    parsed = parse_message_ast('第一段。\n\n<StatusPlaceHolderImpl/>\n\n第二段。')

    assert [segment['type'] for segment in parsed['segments']] == [
        'markdown', 'card-state-placeholder', 'markdown'
    ]
    assert all('StatusPlaceHolderImpl' not in str(segment) for segment in parsed['segments'])


def test_status_placeholder_with_spacing_is_recognized():
    parsed = parse_message_ast('<statusplaceholderimpl />')
    assert parsed['segments'] == [{'type': 'card-state-placeholder'}]
