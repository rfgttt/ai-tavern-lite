import json
from fastapi.testclient import TestClient


def _client(db):
    from app.main import create_app
    from app.db.session import get_db

    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_build_compatibility_report_preserves_unknown_extensions():
    from app.services.cards.compatibility import build_compatibility_report

    report = build_compatibility_report({
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "extensions": {
            "regex_scripts": [
                {"scriptName": "状态栏", "findRegex": "<status>", "replaceString": "<div/>"},
                {"scriptName": "禁用", "disabled": True, "findRegex": "x"},
            ],
            "tavern_helper": {"scripts": [{"name": "MVU", "content": "UpdateVariable JSONPatch"}]},
            "ai_tavern_ui": {
                "schema": "ai-tavern-ui/1",
                "panels": [{"id": "party", "component": "key-value", "source": "/custom/party"}],
            },
            "mystery_extension": {"foo": "bar"},
        },
        "character_book": {
            "entries": [
                {"enabled": True, "keys": ["战斗"], "content": "<battle>"},
                {"enabled": False, "keys": ["禁用"], "content": "<dice>"},
            ]
        },
        "alternate_greetings": ["hello"],
    })

    assert report["card_format"] == "chara_card_v3"
    assert report["capabilities"]["worldbook"] is True
    assert report["capabilities"]["mvu"] is True
    assert report["capabilities"]["battle"] is True
    assert report["capabilities"]["dice"] is False
    assert report["capabilities"]["ui_manifest"] is True
    assert report["counts"]["active_regex_scripts"] == 1
    assert "mystery_extension" in report["unknown_extensions"]
    assert report["ui_manifest"]["schema"] == "ai-tavern-ui/1"


def test_character_compatibility_endpoint(db_with_character):
    db, char = db_with_character
    client = _client(db)

    response = client.get(f"/api/characters/{char.id}/compatibility")

    assert response.status_code == 200
    payload = response.json()
    assert payload["character_id"] == char.id
    assert payload["card_format"] == "chara_card_v3"
    assert payload["capabilities"]["worldbook"] is True


def test_compatibility_report_contains_human_readable_status_details():
    from app.services.cards.compatibility import build_compatibility_report

    report = build_compatibility_report({
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "extensions": {
            "regex_scripts": [{"scriptName": "状态栏", "findRegex": "<status>", "replaceString": "<div/>"}],
            "tavern_helper": {"scripts": [{"name": "MVU", "content": "UpdateVariable JSONPatch 好感度"}]},
        },
        "character_book": {"entries": [{"enabled": True, "keys": ["城堡"], "content": "城堡设定"}]},
    })

    details = {item["key"]: item for item in report["details"]}
    assert details["worldbook"]["label"] == "世界书"
    assert details["worldbook"]["status"] == "supported"
    assert "1 条" in details["worldbook"]["summary"]
    assert details["regex"]["status"] == "partial"
    assert details["mvu"]["status"] == "partial"
    assert details["relationship_state"]["status"] == "partial"
