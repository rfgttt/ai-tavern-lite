from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import json

from ..db.session import get_db
from ..db.models import ChatSession, Message, Character, Memory, TurnSnapshot, Persona, CharacterGroup, GroupMember
from ..schemas import (
    ChatSessionResponse, ChatSessionCreate, ChatSessionUpdate,
    MessageResponse, MessageCreate, MessageUpdate
)
from ..services.character_parser.parser import replace_template_vars
from ..services.settings_service import SettingsService
from ..core.logging import logger
from ..services.runtime.session_service import ensure_session_state
from ..services.runtime.state_engine import serialize_state_document
from ..services.rendering.message_ast import parse_message_ast
from ..services.card_security import is_quarantined

router = APIRouter(tags=["sessions"])


def _touch_session(session: ChatSession) -> None:
    session.updated_at = datetime.now()


@router.get("/sessions", response_model=List[ChatSessionResponse])
def list_sessions(character_id: str = None, db: Session = Depends(get_db)):
    """List chat sessions, optionally filtered by character."""
    query = db.query(ChatSession)
    if character_id:
        query = query.filter(ChatSession.character_id == character_id)
    sessions = query.order_by(ChatSession.updated_at.desc()).all()
    return sessions


@router.post("/sessions", response_model=ChatSessionResponse)
def create_session(session_data: ChatSessionCreate, db: Session = Depends(get_db)):
    """Create a new chat session for a character."""
    character = db.query(Character).filter(Character.id == session_data.character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    try:
        normalized = json.loads(character.normalized_json) if character.normalized_json else {}
    except (json.JSONDecodeError, TypeError):
        normalized = {}
    if is_quarantined(normalized):
        raise HTTPException(
            status_code=423,
            detail="该角色卡处于安全隔离状态，不能创建会话。请先生成安全副本。",
        )

    persona_id = session_data.persona_id
    if persona_id:
        if not db.query(Persona).filter(Persona.id == persona_id).first():
            raise HTTPException(status_code=400, detail="Persona 不存在")
    elif session_data.use_default_persona:
        default_persona = db.query(Persona).filter(Persona.is_default.is_(True)).first()
        persona_id = default_persona.id if default_persona else None
    else:
        persona_id = None

    group_id = session_data.group_id
    if group_id:
        group = db.query(CharacterGroup).filter(CharacterGroup.id == group_id).first()
        if not group:
            raise HTTPException(status_code=400, detail="群组不存在")
        membership = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.character_id == character.id,
        ).first()
        if not membership:
            raise HTTPException(status_code=400, detail="主角色不属于所选群组")

    session = ChatSession(
        character_id=session_data.character_id,
        title=session_data.title or f"与{character.name}的对话",
        persona_id=persona_id,
        group_id=group_id,
    )
    db.add(session)
    db.flush()

    # Initialize runtime before the greeting so the opening message can own an
    # immutable initial-state snapshot instead of falling back to the latest state.
    runtime = ensure_session_state(db, session, character)
    if session_data.initial_state is not None:
        try:
            serialized_state = serialize_state_document(session_data.initial_state)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        runtime.initial_state_json = serialized_state
        runtime.state_json = serialized_state

    opening_message = "" if session_data.skip_opening_message else (
        character.first_message if session_data.opening_message is None else session_data.opening_message
    )
    if opening_message:
        settings = SettingsService.get_all_settings(db)
        username = settings.get("username", "用户")
        first_msg_content = replace_template_vars(
            opening_message, character.name, username
        )

        render_data = parse_message_ast(first_msg_content)
        first_message = Message(
            session_id=session.id,
            role="assistant",
            content=first_msg_content,
            sequence=0,
            generation_status="complete",
            segments_json=json.dumps(render_data["segments"], ensure_ascii=False),
            speaker_metadata_json=json.dumps(render_data["speaker_metadata"], ensure_ascii=False),
            artifacts_json="[]",
            render_version=2,
        )
        db.add(first_message)
        db.flush()
        initial_state = runtime.state_json or runtime.initial_state_json or "{}"
        db.add(TurnSnapshot(
            session_id=session.id,
            message_id=first_message.id,
            state_before_json=initial_state,
            state_after_json=initial_state,
            patch_json="[]",
            events_json="[]",
            choices_json="[]",
            dice_json="[]",
            battle_checks_json="[]",
            battle_json="null",
            expression="",
            triggered_lorebook_json="[]",
            rejected_patch_json="[]",
            parser_errors_json="[]",
        ))

    db.commit()
    db.refresh(session)
    logger.info(f"Session created: {session.id} for character {character.name}")
    return session


@router.put("/sessions/{session_id}", response_model=ChatSessionResponse)
def update_session(
    session_id: str,
    update: ChatSessionUpdate,
    db: Session = Depends(get_db)
):
    """Update session title."""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if update.title is not None:
        session.title = update.title
    if update.persona_id is not None:
        if update.persona_id and not db.query(Persona).filter(Persona.id == update.persona_id).first():
            raise HTTPException(status_code=400, detail="Persona 不存在")
        session.persona_id = update.persona_id or None
    if update.group_id is not None:
        if update.group_id and not db.query(CharacterGroup).filter(CharacterGroup.id == update.group_id).first():
            raise HTTPException(status_code=400, detail="群组不存在")
        session.group_id = update.group_id or None

    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """Delete a chat session."""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    db.query(Memory).filter(Memory.session_id == session_id).delete(synchronize_session=False)
    db.delete(session)
    db.commit()
    logger.info(f"Session deleted: {session_id}")
    return {"success": True}


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_messages(session_id: str, db: Session = Depends(get_db)):
    """Get all messages in a session."""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = db.query(Message).filter(
        Message.session_id == session_id
    ).order_by(Message.sequence.asc()).all()
    return messages


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
def add_message(
    session_id: str,
    msg_data: MessageCreate,
    db: Session = Depends(get_db)
):
    """Manually add a message to a session."""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # Get next sequence number
    last_msg = db.query(Message).filter(
        Message.session_id == session_id
    ).order_by(Message.sequence.desc()).first()
    next_seq = (last_msg.sequence + 1) if last_msg else 0

    message = Message(
        session_id=session_id,
        role=msg_data.role,
        content=msg_data.content,
        sequence=next_seq,
        generation_status="complete"
    )
    db.add(message)
    _touch_session(session)
    db.commit()
    db.refresh(message)
    return message


@router.put("/messages/{message_id}", response_model=MessageResponse)
def update_message(
    message_id: str,
    update: MessageUpdate,
    db: Session = Depends(get_db)
):
    """Update a message (edit content)."""
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    later_message = (
        db.query(Message)
        .filter(Message.session_id == message.session_id, Message.sequence > message.sequence)
        .first()
    )
    if later_message:
        raise HTTPException(
            status_code=409,
            detail="该消息之后已有剧情。请从这里创建分支，或先回滚并删除后续内容。",
        )

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(message, field, value)

    if "content" in update_data:
        render_data = parse_message_ast(message.content or "")
        message.segments_json = json.dumps(render_data["segments"], ensure_ascii=False)
        message.speaker_metadata_json = json.dumps(render_data["speaker_metadata"], ensure_ascii=False)
        message.artifacts_json = "[]"
        message.render_version = 2

    _touch_session(message.session)
    db.commit()
    db.refresh(message)
    return message


@router.delete("/messages/{message_id}")
def delete_message(message_id: str, db: Session = Depends(get_db)):
    """Delete a message."""
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    session = message.session
    later_message = (
        db.query(Message)
        .filter(Message.session_id == session.id, Message.sequence > message.sequence)
        .first()
    )
    if later_message:
        raise HTTPException(
            status_code=409,
            detail="该消息之后已有剧情。请从这里创建分支，或回滚后删除后续内容。",
        )

    snapshot = db.query(TurnSnapshot).filter(TurnSnapshot.message_id == message_id).first()
    if snapshot:
        runtime = ensure_session_state(db, session)
        runtime.state_json = snapshot.state_before_json
        runtime.revision = (runtime.revision or 0) + 1
        db.delete(snapshot)

    db.delete(message)
    _touch_session(session)
    db.commit()
    return {"success": True}


@router.get("/sessions/{session_id}/export")
def export_session(session_id: str, db: Session = Depends(get_db)):
    """Export session as JSON."""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    character = db.query(Character).filter(Character.id == session.character_id).first()

    messages = db.query(Message).filter(
        Message.session_id == session_id
    ).order_by(Message.sequence.asc()).all()

    export_data = {
        "session_id": session.id,
        "title": session.title,
        "character_name": character.name if character else "",
        "created_at": session.created_at.isoformat() if session.created_at else "",
        "updated_at": session.updated_at.isoformat() if session.updated_at else "",
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "sequence": msg.sequence,
                "created_at": msg.created_at.isoformat() if msg.created_at else ""
            }
            for msg in messages
        ]
    }

    return export_data
