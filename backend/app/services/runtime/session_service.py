from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ...db.models import Character, ChatSession, Message, SessionState, TurnSnapshot
from ..settings_service import SettingsService
from .card_profile import analyze_card
from .state_engine import build_initial_state
from ..tavern_compat.initial_state import backfill_card_variables, extract_card_variables


def json_load(value: str | None, default: Any) -> Any:
    try:
        parsed = json.loads(value) if value else default
    except (json.JSONDecodeError, TypeError):
        return default
    return parsed


def character_normalized(character: Character) -> dict:
    value = json_load(character.normalized_json, {})
    return value if isinstance(value, dict) else {}


def character_profile(character: Character) -> dict:
    normalized = character_normalized(character)
    stored = normalized.get("ai_tavern_runtime")
    if isinstance(stored, dict) and stored.get("version") == 3:
        return stored
    return analyze_card(normalized)


def ensure_session_state(
    db: Session,
    session: ChatSession,
    character: Character | None = None,
) -> SessionState:
    runtime = db.query(SessionState).filter(SessionState.session_id == session.id).first()
    character = character or session.character
    if runtime:
        if character is not None:
            normalized = character_normalized(character)
            refreshed_profile = character_profile(character)
            stored_profile = json_load(runtime.profile_json, {})
            profile_changed = (
                stored_profile.get("version") != refreshed_profile.get("version")
                or stored_profile.get("compatibility_core") != refreshed_profile.get("compatibility_core")
            )
            if profile_changed:
                variables = extract_card_variables(normalized).variables
                runtime.profile_json = json.dumps(refreshed_profile, ensure_ascii=False)
                runtime.initial_state_json = json.dumps(
                    backfill_card_variables(json_load(runtime.initial_state_json, {}), variables),
                    ensure_ascii=False,
                )
                runtime.state_json = json.dumps(
                    backfill_card_variables(json_load(runtime.state_json, {}), variables),
                    ensure_ascii=False,
                )
                db.flush()
        return runtime

    if character is None:
        raise ValueError("会话缺少角色")
    normalized = character_normalized(character)
    profile = character_profile(character)
    settings = SettingsService.get_all_settings(db)
    initial_state = build_initial_state(profile, normalized, username=settings.get("username", "用户"))
    runtime = SessionState(
        session_id=session.id,
        profile_json=json.dumps(profile, ensure_ascii=False),
        initial_state_json=json.dumps(initial_state, ensure_ascii=False),
        state_json=json.dumps(initial_state, ensure_ascii=False),
        revision=0,
    )
    db.add(runtime)
    db.flush()
    return runtime


def snapshot_payload(snapshot: TurnSnapshot | None) -> dict | None:
    if snapshot is None:
        return None
    return {
        "id": snapshot.id,
        "message_id": snapshot.message_id,
        "state_before": json_load(snapshot.state_before_json, {}),
        "patch": json_load(snapshot.patch_json, []),
        "state_after": json_load(snapshot.state_after_json, {}),
        "events": json_load(snapshot.events_json, []),
        "choices": json_load(snapshot.choices_json, []),
        "dice": json_load(snapshot.dice_json, []),
        "battle_checks": json_load(snapshot.battle_checks_json, []),
        "battle": json_load(snapshot.battle_json, None),
        "expression": snapshot.expression or "",
        "triggered_lorebook": json_load(snapshot.triggered_lorebook_json, []),
        "rejected_patch": json_load(snapshot.rejected_patch_json, []),
        "parser_errors": json_load(snapshot.parser_errors_json, []),
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def runtime_payload(db: Session, runtime: SessionState) -> dict:
    latest = (
        db.query(TurnSnapshot)
        .join(Message, Message.id == TurnSnapshot.message_id)
        .filter(TurnSnapshot.session_id == runtime.session_id)
        .order_by(Message.sequence.desc())
        .first()
    )
    return {
        "session_id": runtime.session_id,
        "profile": json_load(runtime.profile_json, {}),
        "initial_state": json_load(runtime.initial_state_json, {}),
        "state": json_load(runtime.state_json, {}),
        "revision": runtime.revision or 0,
        "last_turn": snapshot_payload(latest),
        "updated_at": runtime.updated_at,
    }
