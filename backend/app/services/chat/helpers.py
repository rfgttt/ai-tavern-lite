from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ...db.models import Character, ChatSession, GroupMember, Message, Persona


def touch_session(session: ChatSession) -> None:
    session.updated_at = datetime.now()


def safe_json_value(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw) if raw else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def message_payload(message: Message | None) -> dict[str, Any] | None:
    if message is None:
        return None
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "sequence": message.sequence,
        "generation_status": message.generation_status,
        "segments": safe_json_value(getattr(message, "segments_json", "[]"), []),
        "artifacts": safe_json_value(getattr(message, "artifacts_json", "[]"), []),
        "speaker_metadata": safe_json_value(
            getattr(message, "speaker_metadata_json", "{}"), {}
        ),
        "render_version": getattr(message, "render_version", 2) or 2,
        "created_at": (
            message.created_at.isoformat()
            if message.created_at
            else datetime.now().isoformat()
        ),
        "updated_at": (
            message.updated_at.isoformat()
            if message.updated_at
            else datetime.now().isoformat()
        ),
    }


def sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sanitize_error(error: BaseException, *secrets: str) -> str:
    message = str(error) or error.__class__.__name__
    for secret in secrets:
        if secret and secret in message:
            message = message.replace(secret, "***")
    return message


def last_user_content(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content:
            return message.content
    return ""


def lorebook_payload(entries: list[Any], injected_ids: set[Any] | None = None) -> list[dict[str, Any]]:
    injected_ids = (
        injected_ids if injected_ids is not None else {entry.id for entry in entries}
    )
    return [
        {
            "id": entry.id,
            "title": entry.comment or f"条目 #{entry.id}",
            "keys": list(entry.keys)[:12],
            "position": entry.position,
            "content_preview": entry.content.strip()[:240],
            "trigger_type": (
                "constant"
                if entry.constant
                else ("regex" if entry.use_regex else "keyword")
            ),
            "injected": entry.id in injected_ids,
        }
        for entry in entries
    ]


def session_identity_context(
    db: Session,
    session: ChatSession,
) -> tuple[dict[str, str] | None, list[Character]]:
    persona_payload = None
    if getattr(session, "persona_id", None):
        persona = db.query(Persona).filter(Persona.id == session.persona_id).first()
        if persona:
            persona_payload = {
                "name": persona.name,
                "description": persona.description,
                "pronouns": persona.pronouns,
            }

    group_characters: list[Character] = []
    if getattr(session, "group_id", None):
        members = (
            db.query(GroupMember)
            .filter(GroupMember.group_id == session.group_id)
            .order_by(GroupMember.position.asc())
            .all()
        )
        group_characters = [member.character for member in members if member.character]

    return persona_payload, group_characters
