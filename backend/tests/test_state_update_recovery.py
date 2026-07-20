import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.models import Character, Message, SessionState
from app.db.session import get_db
from app.main import create_app
from app.services.diagnostics.service import diagnostic_service
from app.services.settings_service import SettingsService
from app.services.llm.provider import CompletionResult, OpenAICompatibleProvider
from app.services.runtime.state_recovery import (
    allowed_state_targets,
    recover_missing_state_update,
    should_attempt_recovery,
    validate_recovery_operations,
)


def make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            events.append(json.loads(line[6:]))
    return events


def _install_mvu_card(db, character: Character):
    normalized = json.loads(character.normalized_json)
    normalized.pop("ai_tavern_runtime", None)
    normalized["character_book"] = {
        "entries": [
            {
                "id": 2,
                "comment": "变量规则",
                "content": """每轮末尾输出 <UpdateVariable>。好感度和害怕值每轮最多变化2点。
_.add('穗秋生.好感度[0]', 1)
_.insert('穗秋生.重要记忆[0]', '事件')""",
                "constant": True,
                "enabled": True,
                "insertion_order": 999,
                "position": "after_char",
            },
            {
                "id": 5,
                "comment": "[InitVar]",
                "content": json.dumps(
                    {
                        "穗秋生": {
                            "好感度": [5, "[0-100]"],
                            "害怕值": [95, "[0-100]"],
                            "依赖值": [100, "[0-100]"],
                            "重要记忆": [["$__META_EXTENSIBLE__$"], "重要事件"],
                        }
                    },
                    ensure_ascii=False,
                ),
                "constant": False,
                "enabled": False,
            },
        ]
    }
    character.normalized_json = json.dumps(normalized, ensure_ascii=False)
    db.query(SessionState).delete()
    db.commit()


class SequencedProvider:
    def __init__(self, responses, *, cancelled=False):
        self.responses = list(responses)
        self.calls = []
        self._cancelled = cancelled

    @property
    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    async def chat_completion(self, messages, **kwargs):
        self.calls.append({"method": "stream", "messages": messages, "kwargs": kwargs})
        response = self.responses.pop(0)
        for chunk in response:
            yield chunk

    async def complete_once(self, messages, **kwargs):
        self.calls.append({"method": "complete_once", "messages": messages, "kwargs": kwargs})
        response = self.responses.pop(0)
        if isinstance(response, CompletionResult):
            return response
        content = "".join(response) if isinstance(response, list) else str(response)
        return CompletionResult(content=content, finish_reason="stop", response_type="test_completion")


def test_recovery_target_validation_is_declared_only_and_caps_relationship_delta():
    state = {
        "custom": {
            "穗秋生": {
                "好感度": [5, "说明"],
                "重要记忆": [["$__META_EXTENSIBLE__$"], "说明"],
            }
        }
    }
    targets = allowed_state_targets(state)
    operations, events, errors = validate_recovery_operations(
        {
            "operations": [
                {
                    "op": "increment",
                    "path": "/custom/穗秋生/好感度/0",
                    "value": 99,
                    "reason": "温柔安抚",
                },
                {
                    "op": "append",
                    "path": "/custom/穗秋生/重要记忆/0",
                    "value": "第一次得到照顾",
                },
                {"op": "replace", "path": "/api_key", "value": "steal"},
            ]
        },
        targets,
    )

    assert operations == [
        {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 2},
        {"op": "append", "path": "/custom/穗秋生/重要记忆/0", "value": "第一次得到照顾"},
    ]
    assert events == ["温柔安抚"]
    assert any("不在角色卡声明状态" in error for error in errors)


def test_recovery_gate_requires_complete_declared_protocol_and_missing_primary_patch():
    profile = {"capabilities": {"mvu_command_protocol": True}}
    assert should_attempt_recovery(
        profile=profile,
        enabled=True,
        final_status="complete",
        primary_operations=[],
        provider_cancelled=False,
    ) == (True, "primary_response_missing_state_update")
    assert should_attempt_recovery(
        profile=profile,
        enabled=True,
        final_status="complete",
        primary_operations=[{"op": "increment"}],
        provider_cancelled=False,
    )[0] is False
    assert should_attempt_recovery(
        profile=profile,
        enabled=True,
        final_status="stopped",
        primary_operations=[],
        provider_cancelled=False,
    )[0] is False


def test_missing_primary_update_uses_one_safe_fallback_and_applies_state(
    db_with_session, monkeypatch, tmp_path
):
    from app.api import chat as chat_api

    db, character, session = db_with_session
    _install_mvu_card(db, character)
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    SettingsService.update_settings(
        db,
        {
            "mock_llm": False,
            "base_url": "https://example.com/v1",
            "api_key": "sk-fallback-secret",
            "model": "state-test-model",
            "custom_headers": {"X-Auth-Token": "header-fallback-secret"},
        },
    )
    db.add(
        Message(
            session_id=session.id,
            role="assistant",
            content="OLD_HISTORY_SECRET must not reach fallback",
            sequence=2,
            generation_status="complete",
        )
    )
    db.commit()
    provider = SequencedProvider(
        [
            ["她仍然害怕，但因为你的照顾稍微放松了一些。"],
            [
                json.dumps(
                    {
                        "operations": [
                            {
                                "op": "increment",
                                "path": "/custom/穗秋生/好感度/0",
                                "value": 2,
                                "reason": "用户温柔处理伤口",
                            },
                            {
                                "op": "increment",
                                "path": "/custom/穗秋生/害怕值/0",
                                "value": -2,
                                "reason": "用户停止暴力并安抚",
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
            ],
        ]
    )
    monkeypatch.setattr(chat_api, "get_provider", lambda **_kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "我温柔地替她处理伤口。"},
    )
    done = next(item for item in parse_sse(response.text) if item["type"] == "done")
    latest = diagnostic_service.get_latest_request()

    assert response.status_code == 200
    assert len(provider.calls) == 2
    fallback_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "我温柔地替她处理伤口" in fallback_prompt
    assert "她仍然害怕" in fallback_prompt
    assert "API Key" not in fallback_prompt
    assert "sk-fallback-secret" not in fallback_prompt
    assert "header-fallback-secret" not in fallback_prompt
    assert "OLD_HISTORY_SECRET" not in fallback_prompt
    assert done["state"]["relationship"]["affection"] == 7
    assert done["state"]["relationship"]["fear"] == 93
    assert done["revision"] == 1
    assert latest["state"]["state_update_source"] == "fallback_extractor"
    assert latest["state"]["fallback_attempted"] is True
    assert latest["state"]["applied_operations"] == 2


def test_primary_mvu_update_skips_fallback(db_with_session, monkeypatch, tmp_path):
    from app.api import chat as chat_api

    db, character, session = db_with_session
    _install_mvu_card(db, character)
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    provider = SequencedProvider(
        [["正文<UpdateVariable>_.add('穗秋生.好感度[0]', 2);//温柔回应</UpdateVariable>"]]
    )
    monkeypatch.setattr(chat_api, "get_provider", lambda **_kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "安抚她"},
    )
    done = next(item for item in parse_sse(response.text) if item["type"] == "done")
    latest = diagnostic_service.get_latest_request()

    assert len(provider.calls) == 1
    assert done["state"]["relationship"]["affection"] == 7
    assert latest["state"]["state_update_source"] == "primary_response"
    assert latest["state"]["fallback_attempted"] is False


def test_empty_fallback_keeps_revision_and_reports_no_patch(
    db_with_session, monkeypatch, tmp_path
):
    from app.api import chat as chat_api

    db, character, session = db_with_session
    _install_mvu_card(db, character)
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    provider = SequencedProvider([["她沉默了一会儿。"], ['{"operations":[]}']])
    monkeypatch.setattr(chat_api, "get_provider", lambda **_kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "我也保持沉默。"},
    )
    done = next(item for item in parse_sse(response.text) if item["type"] == "done")
    latest = diagnostic_service.get_latest_request()

    assert len(provider.calls) == 2
    assert done["revision"] == 0
    assert latest["state"]["patch_applied"] is False
    assert latest["state"]["state_changed"] is False
    assert latest["state"]["state_update_source"] == "none"
    assert latest["state"]["fallback_attempted"] is True
    assert latest["state"]["applied_operations"] == 0


def test_disabled_recovery_does_not_make_second_request(
    db_with_session, monkeypatch, tmp_path
):
    from app.api import chat as chat_api

    db, character, session = db_with_session
    _install_mvu_card(db, character)
    SettingsService.update_settings(db, {"auto_state_update_recovery": False})
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    provider = SequencedProvider([["她没有表现出明显变化。"]])
    monkeypatch.setattr(chat_api, "get_provider", lambda **_kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "保持距离"},
    )
    done = next(item for item in parse_sse(response.text) if item["type"] == "done")
    latest = diagnostic_service.get_latest_request()

    assert len(provider.calls) == 1
    assert done["revision"] == 0
    assert latest["state"]["fallback_attempted"] is False
    assert latest["state"]["fallback_reason"] == "disabled"


def test_malformed_fallback_is_safe_and_does_not_change_state(
    db_with_session, monkeypatch, tmp_path
):
    from app.api import chat as chat_api

    db, character, session = db_with_session
    _install_mvu_card(db, character)
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    provider = SequencedProvider([["她轻轻点头。"], ["not-json and no state"]])
    monkeypatch.setattr(chat_api, "get_provider", lambda **_kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "问她是否需要休息"},
    )
    done = next(item for item in parse_sse(response.text) if item["type"] == "done")
    latest = diagnostic_service.get_latest_request()

    assert len(provider.calls) == 2
    assert done["revision"] == 0
    assert done["state"]["relationship"]["affection"] == 5
    assert latest["state"]["patch_applied"] is False
    assert latest["state"]["fallback_attempted"] is True
    assert latest["state"]["parser_errors"] >= 1


class _FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class _FakeClient:
    def __init__(self, response):
        self.chat = type("Chat", (), {})()
        self.chat.completions = _FakeCompletions(response)


def _completion_response(
    *,
    content='{"operations":[]}',
    finish_reason="stop",
    reasoning_content="",
    reasoning_tokens=0,
    completion_tokens=0,
):
    message = SimpleNamespace(
        content=content,
        reasoning_content=reasoning_content,
        model_extra={},
    )
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    details = SimpleNamespace(reasoning_tokens=reasoning_tokens)
    usage = SimpleNamespace(
        completion_tokens=completion_tokens,
        completion_tokens_details=details,
    )
    return type("ChatCompletion", (), {"choices": [choice], "usage": usage})()


def test_openai_provider_complete_once_uses_non_stream_message_content(monkeypatch):
    client = _FakeClient(_completion_response(completion_tokens=12))
    provider = OpenAICompatibleProvider("https://example.com/v1", "secret", "model")
    monkeypatch.setattr(provider, "_get_client", lambda: client)

    result = asyncio.run(provider.complete_once(messages=[{"role": "user", "content": "json"}]))

    kwargs = client.chat.completions.kwargs
    assert result.content == '{"operations":[]}'
    assert result.finish_reason == "stop"
    assert result.request_profile == "generic_nonstream"
    assert result.requested_max_tokens == 1024
    assert result.completion_tokens == 12
    assert kwargs["stream"] is False
    assert kwargs["temperature"] == 0.0
    assert kwargs["max_tokens"] == 1024
    assert "top_p" not in kwargs
    assert "extra_body" not in kwargs
    assert "response_format" not in kwargs


def test_official_deepseek_v4_disables_thinking_and_records_usage(monkeypatch):
    client = _FakeClient(
        _completion_response(
            reasoning_content="internal draft must not be parsed",
            reasoning_tokens=7,
            completion_tokens=19,
        )
    )
    provider = OpenAICompatibleProvider(
        "https://api.deepseek.com",
        "secret",
        "deepseek-v4-flash",
    )
    monkeypatch.setattr(provider, "_get_client", lambda: client)

    result = asyncio.run(provider.complete_once(messages=[{"role": "user", "content": "json"}]))

    kwargs = client.chat.completions.kwargs
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert kwargs["stream"] is False
    assert "top_p" not in kwargs
    assert result.request_profile == "deepseek_non_thinking"
    assert result.reasoning_characters == len("internal draft must not be parsed")
    assert result.reasoning_tokens == 7
    assert result.completion_tokens == 19
    assert result.content == '{"operations":[]}'


def test_third_party_gateway_with_deepseek_model_gets_no_vendor_parameter(monkeypatch):
    client = _FakeClient(_completion_response())
    provider = OpenAICompatibleProvider(
        "https://gateway.example/v1",
        "secret",
        "deepseek-v4-flash",
    )
    monkeypatch.setattr(provider, "_get_client", lambda: client)

    result = asyncio.run(provider.complete_once(messages=[{"role": "user", "content": "json"}]))

    assert result.request_profile == "generic_nonstream"
    assert "extra_body" not in client.chat.completions.kwargs


def _recovery_state():
    return {
        "custom": {
            "穗秋生": {
                "好感度": [5, "说明"],
                "重要记忆": [["$__META_EXTENSIBLE__$"], "说明"],
            }
        }
    }


class _OneShotCompletionProvider:
    def __init__(self, result):
        self.result = result
        self._cancelled = False
        self.kwargs = None

    @property
    def cancelled(self):
        return self._cancelled

    async def complete_once(self, **kwargs):
        self.kwargs = kwargs
        return self.result


def _run_recovery(result):
    provider = _OneShotCompletionProvider(result)
    outcome = asyncio.run(
        recover_missing_state_update(
            provider=provider,
            state_before=_recovery_state(),
            user_message="我照顾她。",
            assistant_narrative="她稍微放松。",
            card_rules="好感每轮最多变化2点。",
            custom_headers=None,
        )
    )
    return provider, outcome


def test_recovery_uses_deterministic_1024_token_request():
    provider, outcome = _run_recovery(
        CompletionResult(content='{"operations":[]}', finish_reason="stop")
    )

    assert outcome.reason == "fallback_no_operations"
    assert provider.kwargs["temperature"] == 0.0
    assert provider.kwargs["top_p"] is None
    assert provider.kwargs["max_tokens"] == 1024


def test_reasoning_budget_exhaustion_is_classified_without_parsing_reasoning():
    _provider, outcome = _run_recovery(
        CompletionResult(
            content="",
            finish_reason="length",
            reasoning_characters=900,
            reasoning_tokens=1024,
            completion_tokens=1024,
            requested_max_tokens=1024,
            request_profile="deepseek_non_thinking",
        )
    )

    assert outcome.reason == "fallback_reasoning_budget_exhausted"
    assert outcome.operations == []
    assert outcome.reasoning_tokens == 1024
    assert outcome.request_profile == "deepseek_non_thinking"


def test_length_truncated_json_is_never_applied():
    _provider, outcome = _run_recovery(
        CompletionResult(
            content='{"operations":[{"op":"increment","path":"/custom/穗秋生/好感度/0"',
            finish_reason="length",
        )
    )

    assert outcome.reason == "fallback_output_truncated"
    assert outcome.operations == []


def test_reasoning_content_is_not_used_when_final_content_is_empty():
    _provider, outcome = _run_recovery(
        CompletionResult(
            content="",
            finish_reason="stop",
            reasoning_characters=len('{"operations":[{"op":"increment"}]}'),
        )
    )

    assert outcome.reason == "fallback_empty_response"
    assert outcome.operations == []


def test_stop_with_valid_final_json_still_applies():
    _provider, outcome = _run_recovery(
        CompletionResult(
            content=json.dumps(
                {
                    "operations": [
                        {
                            "op": "increment",
                            "path": "/custom/穗秋生/好感度/0",
                            "value": 1,
                            "reason": "明确照顾",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            finish_reason="stop",
        )
    )

    assert outcome.reason == "fallback_applied"
    assert outcome.operations == [
        {"op": "increment", "path": "/custom/穗秋生/好感度/0", "value": 1}
    ]


def test_empty_fallback_has_specific_diagnostics(db_with_session, monkeypatch, tmp_path):
    from app.api import chat as chat_api

    db, character, session = db_with_session
    _install_mvu_card(db, character)
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    providers = [SequencedProvider([["她沉默。"]]), SequencedProvider([[""]])]
    monkeypatch.setattr(chat_api, "get_provider", lambda **_kwargs: providers.pop(0))

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "保持安静"},
    )
    latest = diagnostic_service.get_latest_request()

    assert response.status_code == 200
    assert latest["state"]["fallback_reason"] == "fallback_empty_response"
    assert latest["state"]["fallback_http_completed"] is True
    assert latest["state"]["fallback_finish_reason"] == "stop"
    assert latest["state"]["fallback_response_type"] == "test_completion"
    assert latest["state"]["fallback_error_type"] == ""


def test_recovery_diagnostics_include_request_profile_and_usage(
    db_with_session, monkeypatch, tmp_path
):
    from app.api import chat as chat_api

    db, character, session = db_with_session
    _install_mvu_card(db, character)
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    provider = SequencedProvider(
        [
            ["她稍微放松。"],
            CompletionResult(
                content='{"operations":[]}',
                finish_reason="stop",
                reasoning_characters=0,
                reasoning_tokens=0,
                completion_tokens=18,
                requested_max_tokens=1024,
                request_profile="deepseek_non_thinking",
            ),
        ]
    )
    monkeypatch.setattr(chat_api, "get_provider", lambda **_kwargs: provider)

    response = make_client(db).post(
        "/api/chat/stream",
        json={"session_id": session.id, "message": "安抚她"},
    )
    latest = diagnostic_service.get_latest_request()

    assert response.status_code == 200
    assert latest["state"]["fallback_request_profile"] == "deepseek_non_thinking"
    assert latest["state"]["fallback_requested_max_tokens"] == 1024
    assert latest["state"]["fallback_completion_tokens"] == 18
    assert latest["state"]["fallback_reasoning_tokens"] == 0
    assert latest["state"]["fallback_reasoning_characters"] == 0
