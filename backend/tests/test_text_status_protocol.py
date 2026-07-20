from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.db.models import Message
from app.db.session import get_db
from app.main import create_app
from app.services.rendering.message_ast import parse_message_ast
from app.services.rendering.status_protocol import parse_status_panel
from app.services.runtime.card_profile import analyze_card


SAMPLE_BLOCK = """<text>
[环境]
📍地点: 游轮客房
🌤️天气: 晴朗
😊心情: 暗流涌动

[角色状态 ]

宁仪 🌙
👔着装: 黑色长裙
🎭行为: 安静观察
💭心绪: 保持警惕

白露 ✨
👔着装: 小熊睡衣
🎭行为: 抱住玩家手臂
💭心绪: 有些吃醋

[💫关系互动]
几人的目光在半空中交锋，气氛微妙。

[🎬场景氛围]
海浪声从舷窗外传来。
<end>"""


def _client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            events.append(json.loads(line[6:]))
    return events


class _Provider:
    cancelled = False

    async def chat_completion(self, messages, **kwargs):
        yield "几人暂时安静下来。\n<te"
        yield SAMPLE_BLOCK[len("<te"):]

    def cancel(self):
        self.cancelled = True


def test_text_end_protocol_becomes_native_status_artifact():
    parsed = parse_message_ast(f"剧情正文。\n\n{SAMPLE_BLOCK}")

    assert parsed["content"] == "剧情正文。"
    assert [segment["type"] for segment in parsed["segments"]] == [
        "markdown",
        "status-panel-placeholder",
    ]
    artifact = parsed["artifacts"][0]
    assert artifact["type"] == "status-panel"
    panel = artifact["data"]
    assert panel["schema"] == "ai-tavern-status-panel/1"
    assert panel["protocol"] == "text-end"
    assert [section["kind"] for section in panel["sections"]] == [
        "environment",
        "characters",
        "interaction",
        "atmosphere",
    ]
    assert panel["sections"][0]["fields"][0] == {
        "label": "地点",
        "value": "游轮客房",
        "icon": "📍",
    }
    assert panel["sections"][1]["characters"][1]["name"] == "白露"
    assert panel["sections"][1]["characters"][1]["fields"][2]["value"] == "有些吃醋"
    assert "<text>" in panel["source_text"]


def test_status_tag_accepts_key_value_only_body():
    parsed = parse_message_ast(
        "正文\n\n<status>\n地点: 图书馆\n时间: 午夜\n氛围: 安静\n</status>"
    )

    panel = parsed["artifacts"][0]["data"]
    assert panel["protocol"] == "status-tag"
    assert panel["sections"][0]["kind"] == "generic"
    assert [field["label"] for field in panel["sections"][0]["fields"]] == [
        "地点",
        "时间",
        "氛围",
    ]


def test_unrecognized_text_tag_is_preserved_as_plain_content():
    content = "正文\n\n<text>这不是结构化状态栏<end>"
    parsed = parse_message_ast(content)

    assert parsed["content"] == content
    assert parsed["artifacts"] == []
    assert not any(segment["type"] == "status-panel-placeholder" for segment in parsed["segments"])


def test_parser_keeps_unknown_sections_and_fields_as_text():
    panel = parse_status_panel(
        "[自定义观察]\n神秘指标: 42\n无法分类的描述",
        protocol="status-tag",
    )

    assert panel is not None
    section = panel["sections"][0]
    assert section["kind"] == "generic"
    assert section["fields"][0]["label"] == "神秘指标"
    assert section["text"] == "无法分类的描述"


def test_card_profile_detects_text_status_protocol():
    profile = analyze_card({
        "name": "状态栏卡",
        "description": "回复末尾必须输出 <text> [环境] [角色状态] <end>",
        "extensions": {},
    })

    assert profile["capabilities"]["text_status_protocol"] is True
    assert "text_status" in profile["native_renderers"]


def test_stream_hides_raw_status_tail_and_persists_native_artifact(db_with_session, monkeypatch):
    db, _character, session = db_with_session
    provider = _Provider()
    monkeypatch.setattr("app.api.chat.get_provider", lambda **kwargs: provider)

    response = _client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "继续"},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    streamed = "".join(event.get("content", "") for event in events if event.get("type") == "content")
    done = next(event for event in events if event.get("type") == "done")

    assert streamed == "几人暂时安静下来。\n"
    assert done["content"] == "几人暂时安静下来。"
    assert done["segments"][-1] == {"type": "status-panel-placeholder", "artifact_index": 0}
    assert done["artifacts"][0]["type"] == "status-panel"
    assert done["artifacts"][0]["data"]["sections"][1]["characters"][0]["name"] == "宁仪"

    message = db.query(Message).filter(Message.id == done["message_id"]).one()
    assert message.content == "几人暂时安静下来。"
    assert json.loads(message.artifacts_json)[0]["type"] == "status-panel"


def test_compatibility_report_exposes_text_status_runtime_check():
    from app.services.cards.compatibility import build_compatibility_report

    report = build_compatibility_report({
        "name": "文本状态卡",
        "description": "必须输出 <text>\n[环境]\n地点: 当前地点\n[角色状态]\n角色A\n心绪: 当前心绪\n<end>",
        "extensions": {},
    })

    assert report["capabilities"]["text_status_protocol"] is True
    assert report["runtime_checks"]["text_status_protocol"]["status"] == "supported"
    assert "text-status-panel" in report["native_renderers"]


def test_runtime_prompt_preserves_detected_text_status_contract():
    from app.services.runtime.prompt import build_runtime_prompt

    prompt = build_runtime_prompt(
        {"mode": "relationship", "capabilities": {"text_status_protocol": True}},
        {"mode": "relationship"},
    )

    assert "<text>...<end>" in prompt
    assert "纯文本区段和键值" in prompt
    assert "<tavern_state>" in prompt
