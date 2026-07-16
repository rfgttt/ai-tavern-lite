from app.services.cards.compatibility import build_compatibility_report
from app.services.runtime.card_profile import analyze_card
from app.services.runtime.output_parser import parse_runtime_output
from app.services.runtime.state_engine import apply_patch, build_initial_state
from app.services.tavern_compat.macros import MacroContext, resolve_safe_macros


def english_helper_card() -> dict:
    import json
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "generic_mvu_card.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


def test_distinct_english_card_uses_same_initializer_patch_and_projection():
    card = english_helper_card()
    profile = analyze_card(card)
    state = build_initial_state(profile, card, username="Morgan")

    assert state["custom"]["Avery"]["affection"] == 11
    assert state["scene"] == {"location": "North Station", "time": "08:10"}
    assert state["relationship"]["stage"] == "new ally"
    assert state["relationship"]["affection"] == 11
    assert state["character"]["state"] == "civilian"
    assert state["character"]["mood"] == "curious"

    parsed = parse_runtime_output(
        '<UpdateVariable><JSONPatch>'
        '[{"op":"replace","path":"/Avery/affection","value":14},'
        '{"op":"replace","path":"/world_state/location","value":"Clock Tower"}]'
        '</JSONPatch></UpdateVariable>'
    )
    result = apply_patch(state, parsed.patch)

    assert result.rejected == []
    assert result.state["custom"]["Avery"]["affection"] == 14
    assert result.state["relationship"]["affection"] == 14
    assert result.state["scene"]["location"] == "Clock Tower"


def test_distinct_english_card_uses_safe_macros_and_runtime_report():
    card = english_helper_card()
    state = build_initial_state(analyze_card(card), card, username="Morgan")
    context = MacroContext(char_name="Avery", user_name="Morgan", runtime_state=state)

    rendered = resolve_safe_macros(
        '<user> meets <char>: {{getvar::stat_data.Avery.affection}}\n'
        '{{format_message_variable::stat_data}}',
        context,
    )
    report = build_compatibility_report(card)

    assert rendered.startswith("Morgan meets Avery: 11")
    assert '"brass key"' in rendered
    assert report["runtime_checks"]["initial_variables"]["status"] == "supported"
    assert report["runtime_checks"]["external_javascript"]["status"] == "isolated"
    assert report["runtime_checks"]["status_placeholder"]["status"] == "supported"


def test_chinese_initvar_fixture_uses_the_same_compatibility_core():
    import json
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "tavern_helper_mvu_card.json"
    card = json.loads(fixture.read_text(encoding="utf-8"))
    state = build_initial_state(analyze_card(card), card, username="林舟")
    report = build_compatibility_report(card)

    assert state["custom"]["霜叶"]["好感度"] == 20
    assert state["scene"]["location"] == "月台"
    assert state["relationship"]["affection"] == 20
    assert state["character"]["state"] == "日常"
    assert report["runtime_checks"]["initial_variables"]["source"] == "worldbook:[initvar]"
    assert report["runtime_checks"]["external_javascript"]["status"] == "isolated"
