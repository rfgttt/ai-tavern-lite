from __future__ import annotations

import json
from types import SimpleNamespace


def executable_card() -> dict:
    return {
        "name": "穗秋生",
        "first_mes": "开场正文\n<StatusPlaceHolderImpl/>",
        "extensions": {
            "regex_scripts": [
                {
                    "scriptName": "状态栏美化",
                    "findRegex": "<StatusPlaceHolderImpl/>",
                    "replaceString": "<script>Vue.mount()</script><div class='status-container night-sky'>重要记忆 上一页 下一页</div>",
                    "promptOnly": False,
                    "disabled": False,
                },
                {
                    "scriptName": "对 AI 隐藏状态栏",
                    "findRegex": "<StatusPlaceHolderImpl/>",
                    "replaceString": "",
                    "promptOnly": True,
                    "disabled": False,
                },
                {
                    "scriptName": "隐藏变量",
                    "findRegex": "/<UpdateVariable>[\\s\\S]*?<\\/UpdateVariable>/gm",
                    "replaceString": "",
                    "promptOnly": True,
                    "disabled": False,
                },
            ],
            "tavern_helper": [
                ["scripts", [{
                    "type": "script",
                    "enabled": True,
                    "name": "MVUbeta",
                    "content": "import 'https://example.invalid/mvu.js'",
                    "button": {"buttons": [
                        {"name": "重新处理变量", "visible": True},
                        {"name": "重新读取初始变量", "visible": True},
                    ]},
                }]],
                ["variables", {}],
            ],
        },
        "character_book": {"entries": []},
    }


def test_emulation_manifest_keeps_intent_but_not_executable_source():
    from app.services.tavern_compat.emulation import extract_safe_emulation

    manifest = extract_safe_emulation(executable_card())
    serialized = json.dumps(manifest, ensure_ascii=False)

    assert manifest["status_panel"]["enabled"] is True
    assert manifest["status_panel"]["theme"] == "night_sky"
    assert manifest["status_panel"]["memory_page_size"] == 1
    assert manifest["prompt_filters"]["status_placeholder"] is True
    assert {item["id"] for item in manifest["native_actions"]} == {
        "reprocess_variables", "restore_initial_state"
    }
    reprocess = next(item for item in manifest["native_actions"] if item["id"] == "reprocess_variables")
    assert reprocess["status"] == "automatic"
    assert "Vue.mount" not in serialized
    assert "example.invalid" not in serialized
    assert "<script" not in serialized


def test_safe_copy_preserves_declarative_emulation_and_removes_code():
    from app.services.card_security import sanitize_character_card, scan_character_card

    card = executable_card()
    raw = {"data": card}
    report = scan_character_card(card, raw)
    safe, safe_raw, changes = sanitize_character_card(card, raw, report)

    extensions = safe["extensions"]
    assert "regex_scripts" not in extensions
    assert "tavern_helper" not in extensions
    assert extensions["ai_tavern_emulation"]["status_panel"]["theme"] == "night_sky"
    assert "转换为原生安全兼容清单" in "；".join(changes)
    serialized = json.dumps(safe_raw, ensure_ascii=False)
    assert "Vue.mount" not in serialized
    assert "example.invalid" not in serialized


def test_history_protocol_blocks_are_removed_before_model_prompt(db_with_character):
    from app.services.prompt_builder.builder import PromptBuilder

    _db, character = db_with_character
    normalized = json.loads(character.normalized_json)
    normalized.setdefault("extensions", {})["ai_tavern_emulation"] = {
        "prompt_filters": {"status_placeholder": True, "update_variable": True, "analysis": True}
    }
    character.normalized_json = json.dumps(normalized, ensure_ascii=False)
    messages = [
        SimpleNamespace(
            role="assistant",
            sequence=0,
            content=(
                "可见剧情\n<StatusPlaceHolderImpl/>\n"
                "<UpdateVariable><Analysis>草稿</Analysis>_.add('x',1)</UpdateVariable>"
            ),
        )
    ]

    built = PromptBuilder(character, context_window=2048, max_new_tokens=256).build(
        messages=messages,
        lorebook_entries=[],
        memories=[],
        runtime_profile={},
        runtime_state={},
    )
    history = "\n".join(item["content"] for item in built.messages[1:])

    assert "可见剧情" in history
    assert "StatusPlaceHolderImpl" not in history
    assert "UpdateVariable" not in history
    assert "草稿" not in history


def test_runtime_profile_exposes_native_emulation():
    from app.services.runtime.card_profile import analyze_card

    profile = analyze_card(executable_card())

    assert profile["version"] == 8
    assert profile["script_execution"] == "safe-native-emulation"
    assert profile["emulation"]["status_panel"]["enabled"] is True
    assert profile["regex_script_count"] == 3
