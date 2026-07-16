import json


def test_parse_message_ast_recognizes_speakers_narration_and_actions():
    from app.services.rendering.message_ast import parse_message_ast

    parsed = parse_message_ast(
        '*火把轻轻摇晃。*\n\n艾琳：“别碰那扇门。”\n\n莉亚: “但宝藏就在后面！”\n\n**艾琳暗自提高了警惕。**'
    )

    assert [item["type"] for item in parsed["segments"]] == [
        "narration", "dialogue", "dialogue", "thought"
    ]
    assert parsed["segments"][1]["speaker"] == "艾琳"
    assert parsed["segments"][2]["speaker"] == "莉亚"
    assert parsed["speaker_metadata"]["艾琳"]["color"].startswith("hsl(")
    assert parsed["speaker_metadata"]["艾琳"]["color"] == parse_message_ast('艾琳：“再次说话。”')["speaker_metadata"]["艾琳"]["color"]


def test_message_response_exposes_legacy_parsed_segments(db_with_session):
    from app.schemas import MessageResponse

    db, _, session = db_with_session
    message = session.messages[0]
    message.content = '林夕：“欢迎回来。”'
    message.segments_json = '[]'
    message.artifacts_json = '[]'
    message.speaker_metadata_json = '{}'
    db.commit()

    response = MessageResponse.model_validate(message).model_dump()

    assert response["segments"][0]["type"] == "dialogue"
    assert response["segments"][0]["speaker"] == "林夕"
    assert response["render_version"] == 2
